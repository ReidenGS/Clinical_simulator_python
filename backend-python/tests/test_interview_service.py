from __future__ import annotations

import unittest

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


if __name__ == '__main__':
    unittest.main()
