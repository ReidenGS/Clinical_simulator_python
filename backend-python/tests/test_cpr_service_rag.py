from __future__ import annotations

import unittest

from app.services.cpr_guideline_rag import CprGuidelineContext
from app.services.cpr_service import CprService


class FakeGuidelineRag:
    def get_guideline_context(self, config=None):
        return CprGuidelineContext(
            summary='Use 90-100 CPM for this simulated protocol and defibrillate quickly with minimal pauses.',
            standards={
                'compression_rate_min': 90,
                'compression_rate_max': 100,
                'depth_cm_min': 5.0,
                'depth_cm_max': 6.0,
                'compression_fraction_min': 0.5,
                'full_recoil_required': True,
                'minimize_interruptions': True,
                'avoid_excessive_ventilation': True,
                'defibrillation_guidance': 'Defibrillate as soon as practical while compressions continue during setup.',
            },
            source_url='https://example.com/guideline',
            source_title='Example Guideline',
            fetched_at=0,
        )


class CprServiceRagTests(unittest.TestCase):
    def test_evaluate_uses_rag_rate_window_and_feedback_metadata(self) -> None:
        service = CprService()
        service.guideline_rag = FakeGuidelineRag()

        state = {
            'averageRate': 95,
            'visibleRatio': 0.9,
            'straightArmRatio': 0.9,
            'centeredRatio': 0.9,
            'checklist': [
                {'id': 'a', 'label': 'x', 'completed': True, 'detail': 'ok'},
                {'id': 'b', 'label': 'y', 'completed': True, 'detail': 'ok'},
            ],
            'depthProxyAverage': 0.35,
            'recoilRatio': 0.85,
            'compressionFraction': 0.7,
            'rateConsistency': 85,
            'elapsedSeconds': 45,
            'cycleHistory': [],
            'currentRate': 95,
            'maxRate': 108,
        }
        scenario = {
            'targetCompressionRate': {'min': 100, 'max': 120},
        }
        rubric = {
            'weights': {
                'rhythm': 35,
                'form': 25,
                'readiness': 5,
                'depthProxy': 10,
                'recoil': 10,
                'compressionFraction': 10,
                'rateConsistency': 5,
            },
            'thresholds': {
                'visibleRatio': 0.7,
                'straightArmRatio': 0.65,
                'centeredRatio': 0.65,
            },
        }

        result = service.evaluate(state, scenario, rubric)

        self.assertGreaterEqual(result['evaluation']['breakdown']['rhythm'], 95)
        self.assertIn('90-100', ' '.join(result['evaluation']['strengths']))
        self.assertEqual(result['feedback']['guidelineSource'], 'https://example.com/guideline')
        self.assertIn('defibrillate quickly', result['feedback']['guidelineSummary'].lower())


if __name__ == '__main__':
    unittest.main()
