from __future__ import annotations

import unittest

from app.services.case_generator_service import CaseGeneratorService
from app.services.interview_redflag_rag import RedFlagContext


class FakeRedFlagRagService:
    def get_red_flag_context(self, diagnosis_hint: str, difficulty: str, config: dict):
        return RedFlagContext(
            red_flags=[
                'hemoptysis',
                'shortness of breath at rest',
                'new confusion',
            ],
            source_urls=['https://www.nhs.uk/example'],
            source_mode='web+offline',
        )


class CaseGeneratorRedFlagTests(unittest.TestCase):
    def test_enrich_red_flags_merges_flags_and_raises_critical_floor(self):
        service = CaseGeneratorService()
        service.redflag_rag = FakeRedFlagRagService()

        case_data = {
            'correctDiagnosis': 'Pneumonia',
            'difficulty': 'medium',
            'redFlags': ['persistent fever'],
            'mustAskItems': [
                {'dimension': 'HPC', 'subItem': 'cough duration', 'critical': False, 'hint': 'How long?'},
                {'dimension': 'PMH', 'subItem': 'comorbidities', 'critical': False, 'hint': 'Any diseases?'},
                {'dimension': 'ROS', 'subItem': 'chest pain', 'critical': False, 'hint': 'Any chest pain?'},
                {'dimension': 'ICE', 'subItem': 'concerns', 'critical': False, 'hint': 'Any concerns?'},
            ],
        }

        service._enrich_red_flags(case_data, {'textProvider': 'OPENAI'})

        self.assertIn('persistent fever', case_data['redFlags'])
        self.assertIn('hemoptysis', case_data['redFlags'])
        self.assertIn('new confusion', case_data['redFlags'])
        self.assertGreaterEqual(len(case_data['redFlags']), 4)

        critical_count = sum(1 for item in case_data['mustAskItems'] if item.get('critical'))
        self.assertGreaterEqual(critical_count, 4)

        ros_screeners = [
            item for item in case_data['mustAskItems']
            if str(item.get('dimension')) == 'ROS' and str(item.get('subItem', '')).startswith('screen for')
        ]
        self.assertTrue(ros_screeners)


if __name__ == '__main__':
    unittest.main()
