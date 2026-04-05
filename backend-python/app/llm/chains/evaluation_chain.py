from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.llm.clients import LangChainModelFactory
from app.llm.prompts.evaluation_prompts import EVALUATION_PROMPT_VERSION, build_dimension_evaluation_prompt
from app.llm.resilience import invoke_with_retry

if TYPE_CHECKING:
    from app.llm.schemas.interview_outputs import DimensionEvaluationOutput


class InterviewEvaluationChain:
    def __init__(self) -> None:
        self.factory = LangChainModelFactory()
        self.settings = get_settings()
        self.output_schema = self._get_output_schema()
        self.parser = self._build_parser()

    def _get_output_schema(self):
        from app.llm.schemas.interview_outputs import DimensionEvaluationOutput

        return DimensionEvaluationOutput

    def _build_parser(self):
        from langchain_core.output_parsers import PydanticOutputParser

        return PydanticOutputParser(pydantic_object=self.output_schema)

    def invoke(
        self,
        dim: dict,
        session_state: dict,
        diagnosis: str,
        case_data: dict,
        config: dict,
    ) -> 'DimensionEvaluationOutput':
        model = self.factory.build_chat_model(
            provider=config['textProvider'],
            temperature=0.2,
            model=config.get('textModel'),
            api_key=config.get('textApiKey'),
            base_url=config.get('textBaseUrl'),
        )
        prompt = build_dimension_evaluation_prompt(
            dim=dim,
            session_state=session_state,
            diagnosis=diagnosis,
            case_data=case_data,
            format_instructions=self.parser.get_format_instructions(),
        )

        structured_model = model.with_structured_output(self.output_schema)
        structured_chain = prompt | structured_model
        fallback_chain = prompt | model | self.parser

        try:
            return invoke_with_retry(
                lambda: structured_chain.invoke(
                    {},
                    config={
                        'run_name': 'interview_dimension_evaluation',
                        'tags': ['clinical-simulator', 'interview-eval', f'prompt:{EVALUATION_PROMPT_VERSION}'],
                        'metadata': {
                            'prompt_version': EVALUATION_PROMPT_VERSION,
                            'dimension_id': dim.get('id'),
                            'rag_active': bool(session_state.get('ragCaseSummary')),
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
                lambda: fallback_chain.invoke({}),
                retries=1,
                backoff_seconds=self.settings.langchain_retry_backoff_seconds,
            )
