from __future__ import annotations

import unittest
from dataclasses import dataclass

from app.services.interview_service import InterviewService


CASE_DATA = {
    'name': 'Chest Pain Case',
    'mustAskItems': [
        {'dimension': 'HPC', 'subItem': 'onset of pain', 'critical': True, 'hint': 'When did the pain start?'},
        {'dimension': 'PMH', 'subItem': 'past cardiac history', 'critical': False},
        {'dimension': 'ICE', 'subItem': 'patient concerns', 'critical': False},
        {'dimension': 'ROS', 'subItem': 'shortness of breath', 'critical': True, 'hint': 'Ask about breathing symptoms.'},
    ],
}


@dataclass
class FakeRetrievedCase:
    case_id: str
    description: str
    summary: str


class FakeRagService:
    def __init__(self) -> None:
        self.calls = 0

    def sample_case(self):
        self.calls += 1
        return FakeRetrievedCase(
            case_id='open-patient-1',
            description='62-year-old male with exertional chest pain and dyspnea, worse over 3 months.',
            summary='fallback summary',
        )


class FakeAIService:
    def __init__(self) -> None:
        self.calls = 0

    def generate_text(self, **kwargs):
        self.calls += 1
        return 'LLM summary: older male with progressive exertional dyspnea and chest discomfort.'


class FakeParsed:
    def __init__(self) -> None:
        self.patient_response = 'I feel short of breath when walking.'
        self.extraction = None


class FakeTurnChain:
    def __init__(self) -> None:
        self.invocations: list[dict] = []

    def invoke(self, **kwargs):
        self.invocations.append(kwargs)
        return FakeParsed()


class InterviewServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = InterviewService()

    def test_create_initial_state_builds_dimension_coverages(self) -> None:
        state = self.service.create_initial_state(CASE_DATA)
        self.assertEqual(state['phase'], 'OPENING')
        hpc = next(dim for dim in state['dimensionCoverages'] if dim['dimension'] == 'HPC')
        self.assertEqual(hpc['totalItems'], 1)
        self.assertEqual(hpc['percentage'], 0)

    def test_update_coverage_tracks_new_items_and_updates_percentage(self) -> None:
        state = self.service.create_initial_state(CASE_DATA)
        extraction = {
            'topicsCovered': [
                {'dimension': 'HPC', 'subItem': 'onset', 'confidence': 0.9},
                {'dimension': 'ROS', 'subItem': 'shortness of breath', 'confidence': 0.95},
            ]
        }

        had_progress = self.service.update_coverage(state, CASE_DATA, extraction)

        self.assertTrue(had_progress)
        self.assertEqual(state['overallCoverage'], 50)
        self.assertEqual(len(state['events']), 1)
        self.assertEqual(state['events'][0]['type'], 'coverage_update')

    def test_check_phase_transition_advances_with_progress(self) -> None:
        state = self.service.create_initial_state(CASE_DATA)
        state['turnCount'] = 1
        state['overallCoverage'] = 25

        self.service.check_phase_transition(state)

        self.assertEqual(state['phase'], 'HISTORY_TAKING')

    def test_evaluate_decision_returns_hint_after_stall(self) -> None:
        state = self.service.create_initial_state(CASE_DATA)
        state['turnCount'] = 5
        state['turnsWithoutProgress'] = 3

        decision = self.service.evaluate_decision(state, CASE_DATA)

        self.assertEqual(decision['type'], 'HINT_NEEDED')
        self.assertIn('When did the pain start?', decision['message'])

    def test_process_turn_persists_single_rag_case_for_session(self) -> None:
        fake_chain = FakeTurnChain()
        fake_rag = FakeRagService()
        fake_ai = FakeAIService()
        self.service._turn_chain = fake_chain
        self.service.rag_service = fake_rag
        self.service.ai_service = fake_ai

        config = {'textProvider': 'OPENAI'}

        first = self.service.process_turn(
            case_data=CASE_DATA,
            history=[],
            student_input='Can you describe your symptoms?',
            state=None,
            config=config,
        )
        first_state = first['sessionState']

        self.assertEqual(first_state['ragCaseId'], 'open-patient-1')
        self.assertIn('LLM summary', first_state['ragCaseSummary'])
        self.assertEqual(fake_rag.calls, 1)
        self.assertEqual(fake_ai.calls, 1)
        self.assertEqual(fake_chain.invocations[0]['rag_case_summary'], first_state['ragCaseSummary'])

        second = self.service.process_turn(
            case_data=CASE_DATA,
            history=[{'role': 'patient', 'text': first['patientMessage']['text']}],
            student_input='What makes it worse?',
            state=first_state,
            config=config,
        )
        second_state = second['sessionState']

        self.assertEqual(second_state['ragCaseId'], 'open-patient-1')
        self.assertEqual(second_state['ragCaseSummary'], first_state['ragCaseSummary'])
        self.assertEqual(fake_rag.calls, 1)
        self.assertEqual(fake_ai.calls, 1)
        self.assertEqual(fake_chain.invocations[1]['rag_case_summary'], first_state['ragCaseSummary'])


if __name__ == '__main__':
    unittest.main()
