from __future__ import annotations

import unittest

from app.services.interview_evaluate_service import InterviewEvaluateService


SESSION_STATE = {
    'overallCoverage': 80,
    'turnCount': 10,
    'phase': 'GUIDED_INQUIRY',
    'dimensionCoverages': [
        {'dimension': 'HPC', 'coveredItems': ['onset', 'severity'], 'percentage': 100},
        {'dimension': 'ROS', 'coveredItems': ['sob'], 'percentage': 50},
    ],
    'extractions': [],
}


class InterviewEvaluateServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = InterviewEvaluateService()

    def test_score_deterministic_info_gathering(self) -> None:
        result = self.service.score_deterministic('info_gathering', SESSION_STATE)
        self.assertEqual(result['rawScore'], 80)
        self.assertIn('Excellent history taking', result['feedback'])
        self.assertTrue(result['evidence'])

    def test_score_deterministic_efficiency(self) -> None:
        result = self.service.score_deterministic('efficiency', SESSION_STATE)
        self.assertEqual(result['rawScore'], 100)
        self.assertIn('10 turns', result['feedback'])

    def test_determine_competency(self) -> None:
        thresholds = {'expert': 85, 'proficient': 70, 'competent': 55, 'beginner': 40}
        self.assertEqual(self.service.determine_competency(72, thresholds), 'proficient')
        self.assertEqual(self.service.determine_competency(30, thresholds), 'novice')


if __name__ == '__main__':
    unittest.main()
