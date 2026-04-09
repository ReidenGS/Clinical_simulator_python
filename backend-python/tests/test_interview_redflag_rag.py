from __future__ import annotations

import unittest

from app.services.interview_redflag_rag import InterviewRedFlagRagService


class InterviewRedFlagRagTests(unittest.TestCase):
    def test_offline_match_short_circuits_web_lookup(self):
        service = InterviewRedFlagRagService()

        def fail_search(_: str):
            raise AssertionError('web search should not run when offline rule matches')

        service._search_snippets = fail_search  # type: ignore[method-assign]
        ctx = service.get_red_flag_context(
            diagnosis_hint='Pneumonia',
            difficulty='medium',
            config={'textProvider': 'OPENAI'},
        )

        self.assertEqual(ctx.source_mode, 'offline')
        self.assertTrue(ctx.red_flags)
        self.assertFalse(ctx.source_urls)


if __name__ == '__main__':
    unittest.main()
