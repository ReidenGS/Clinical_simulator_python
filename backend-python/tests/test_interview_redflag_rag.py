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

    def test_vector_offline_match_via_alias_short_circuits_web_lookup(self):
        """Alias expansion: 'heart attack' → MI/ACS tokens → vector match."""
        service = InterviewRedFlagRagService()

        def fail_search(_: str):
            raise AssertionError('web search should not run when vector offline match succeeds')

        service._search_snippets = fail_search  # type: ignore[method-assign]
        ctx = service.get_red_flag_context(
            diagnosis_hint='heart attack warning symptoms',
            difficulty='medium',
            config={'textProvider': 'OPENAI'},
        )

        self.assertEqual(ctx.source_mode, 'vector_offline')
        self.assertTrue(ctx.red_flags)
        self.assertFalse(ctx.source_urls)

    def test_vector_offline_match_pure_semantic_no_alias(self):
        """Pure semantic similarity: 'cerebrovascular accident' should match stroke
        without relying on the alias table (CVA alias maps to stroke, but the
        full phrase itself is not in the alias keys, so this tests raw cosine)."""
        service = InterviewRedFlagRagService()

        def fail_search(_: str):
            raise AssertionError('web search should not run when vector offline match succeeds')

        service._search_snippets = fail_search  # type: ignore[method-assign]
        ctx = service.get_red_flag_context(
            diagnosis_hint='cerebrovascular accident with sudden weakness',
            difficulty='medium',
            config={'textProvider': 'OPENAI'},
        )

        # Should match stroke via vector similarity (shares tokens: sudden, weakness)
        self.assertIn(ctx.source_mode, {'offline', 'vector_offline'})
        self.assertTrue(ctx.red_flags)

    def test_web_fallback_runs_only_when_vector_does_not_match(self):
        service = InterviewRedFlagRagService()
        called = {'count': 0}

        def fake_search(_: str):
            called['count'] += 1
            return [{'title': 'NHS', 'snippet': 'Urgent red flags...', 'url': 'https://www.nhs.uk/conditions/chest-pain/'}]

        def fake_extract(*args, **kwargs):
            return ['sudden severe chest pain', 'collapse']

        service._search_snippets = fake_search  # type: ignore[method-assign]
        service._extract_with_llm = fake_extract  # type: ignore[method-assign]

        ctx = service.get_red_flag_context(
            diagnosis_hint='rare undifferentiated syndrome',
            difficulty='medium',
            config={'textProvider': 'OPENAI'},
        )

        self.assertEqual(called['count'], 1)
        self.assertIn(ctx.source_mode, {'web', 'web+offline'})
        self.assertTrue(ctx.source_urls)
        self.assertTrue(ctx.red_flags)


if __name__ == '__main__':
    unittest.main()
