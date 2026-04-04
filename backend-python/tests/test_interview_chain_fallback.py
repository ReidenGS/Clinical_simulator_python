from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


class FakeParser:
    def get_format_instructions(self) -> str:
        return 'Return structured output.'


class FakeRunnable:
    def __init__(self, result=None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[tuple[object, object]] = []

    def __or__(self, other):
        return self

    def invoke(self, payload, config=None):
        self.calls.append((payload, config))
        if self.error is not None:
            raise self.error
        return self.result


class FakePrompt:
    def __init__(self, structured_runnable: FakeRunnable, fallback_runnable: FakeRunnable):
        self.structured_runnable = structured_runnable
        self.fallback_runnable = fallback_runnable
        self._step = 0

    def __or__(self, other):
        self._step += 1
        if self._step == 1:
            return self.structured_runnable
        return self.fallback_runnable


class InterviewChainFallbackTests(unittest.TestCase):
    def test_interview_turn_chain_falls_back_when_structured_output_fails(self):
        from app.llm.chains.interview_chain import InterviewTurnChain

        structured = FakeRunnable(error=RuntimeError('schema failure'))
        fallback_result = SimpleNamespace(patient_response='I started feeling this yesterday.')
        fallback = FakeRunnable(result=fallback_result)

        with patch.object(InterviewTurnChain, '_get_output_schema', return_value=object()), \
             patch.object(InterviewTurnChain, '_build_parser', return_value=FakeParser()), \
             patch.object(InterviewTurnChain, '_build_history_messages', return_value=[]), \
             patch('app.llm.chains.interview_chain.build_patient_turn_prompt', return_value=FakePrompt(structured, fallback)), \
             patch('app.llm.chains.interview_chain.LangChainModelFactory') as factory_cls:
            model = Mock()
            model.with_structured_output.return_value = object()
            factory_cls.return_value.build_chat_model.return_value = model

            chain = InterviewTurnChain()
            result = chain.invoke(
                case_data={
                    'name': 'Case',
                    'age': 50,
                    'gender': 'male',
                    'correctDiagnosis': 'angina',
                    'initialComplaint': 'chest pain',
                    'hiddenDetails': {
                        'duration': '1 day',
                        'triggers': 'exercise',
                        'pastHistory': 'HTN',
                        'associatedSymptoms': 'sweating',
                        'lifestyle': 'smoker',
                    },
                    'mustAskItems': [],
                },
                history=[{'role': 'student', 'text': 'When did it start?'}],
                student_input='Tell me more about the pain.',
                config={'textProvider': 'OPENAI'},
            )

        self.assertEqual(result.patient_response, 'I started feeling this yesterday.')
        self.assertEqual(len(structured.calls), 3)
        self.assertEqual(len(fallback.calls), 1)

    def test_evaluation_chain_falls_back_when_structured_output_fails(self):
        from app.llm.chains.evaluation_chain import InterviewEvaluationChain

        structured = FakeRunnable(error=RuntimeError('structured output unavailable'))
        fallback_result = SimpleNamespace(
            raw_score=76,
            feedback='Reasonable clinical reasoning.',
            evidence=['Asked focused questions'],
        )
        fallback = FakeRunnable(result=fallback_result)

        with patch.object(InterviewEvaluationChain, '_get_output_schema', return_value=object()), \
             patch.object(InterviewEvaluationChain, '_build_parser', return_value=FakeParser()), \
             patch('app.llm.chains.evaluation_chain.build_dimension_evaluation_prompt', return_value=FakePrompt(structured, fallback)), \
             patch('app.llm.chains.evaluation_chain.LangChainModelFactory') as factory_cls:
            model = Mock()
            model.with_structured_output.return_value = object()
            factory_cls.return_value.build_chat_model.return_value = model

            chain = InterviewEvaluationChain()
            result = chain.invoke(
                dim={'id': 'clinical_reasoning', 'name': 'Clinical reasoning', 'description': 'Evaluate reasoning'},
                session_state={
                    'turnCount': 6,
                    'phase': 'GUIDED_INQUIRY',
                    'overallCoverage': 70,
                    'dimensionCoverages': [],
                    'extractions': [],
                },
                diagnosis='ACS',
                case_data={
                    'name': 'Case',
                    'age': 50,
                    'gender': 'male',
                    'correctDiagnosis': 'angina',
                },
                config={'textProvider': 'OPENAI'},
            )

        self.assertEqual(result.raw_score, 76)
        self.assertEqual(result.feedback, 'Reasonable clinical reasoning.')
        self.assertEqual(len(structured.calls), 3)
        self.assertEqual(len(fallback.calls), 1)


if __name__ == '__main__':
    unittest.main()
