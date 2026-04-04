from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.llm.clients import LangChainModelFactory
from app.llm.prompts.interview_prompts import INTERVIEW_PROMPT_VERSION, build_patient_turn_prompt
from app.llm.resilience import invoke_with_retry

if TYPE_CHECKING:
    from app.llm.schemas.interview_outputs import PatientTurnOutput


class InterviewTurnChain:
    def __init__(self) -> None:
        self.factory = LangChainModelFactory()
        self.settings = get_settings()
        self.output_schema = self._get_output_schema()
        self.parser = self._build_parser()

    def _get_output_schema(self):
        from app.llm.schemas.interview_outputs import PatientTurnOutput

        return PatientTurnOutput

    def _build_parser(self):
        from langchain_core.output_parsers import PydanticOutputParser

        return PydanticOutputParser(pydantic_object=self.output_schema)

    def _build_history_messages(self, history: list[dict[str, str]]) -> list[object]:
        from langchain_core.messages import AIMessage, HumanMessage

        history_messages: list[object] = []
        for message in history:
            role = message['role']
            content = message['text']
            if role == 'student':
                history_messages.append(HumanMessage(content=content))
            elif role in {'patient', 'coach'}:
                history_messages.append(AIMessage(content=content))
        return history_messages

    def invoke(
        self,
        case_data: dict,
        history: list[dict[str, str]],
        student_input: str,
        config: dict,
    ) -> 'PatientTurnOutput':
        prompt = build_patient_turn_prompt(case_data, self.parser.get_format_instructions())
        model = self.factory.build_chat_model(
            provider=config['textProvider'],
            temperature=0.4,
            model=config.get('textModel'),
            api_key=config.get('textApiKey'),
            base_url=config.get('textBaseUrl'),
        )
        payload = {
            'history_messages': self._build_history_messages(history),
            'student_input': student_input,
        }

        structured_model = model.with_structured_output(self.output_schema)
        structured_chain = prompt | structured_model
        fallback_chain = prompt | model | self.parser

        try:
            return invoke_with_retry(
                lambda: structured_chain.invoke(
                    payload,
                    config={
                        'run_name': 'interview_turn',
                        'tags': ['clinical-simulator', 'interview', f'prompt:{INTERVIEW_PROMPT_VERSION}'],
                        'metadata': {
                            'prompt_version': INTERVIEW_PROMPT_VERSION,
                            'langsmith_enabled': self.settings.langsmith_enabled,
                            'langsmith_project': self.settings.langsmith_project,
                        },
                    },
                ),
                retries=self.settings.langchain_max_retries,
                backoff_seconds=self.settings.langchain_retry_backoff_seconds,
            )
        except Exception:
            return invoke_with_retry(
                lambda: fallback_chain.invoke(payload),
                retries=1,
                backoff_seconds=self.settings.langchain_retry_backoff_seconds,
            )
