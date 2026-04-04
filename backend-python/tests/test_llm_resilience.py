from __future__ import annotations

import unittest
from unittest.mock import patch

from app.llm.resilience import invoke_with_retry


class RetryHelperTests(unittest.TestCase):
    def test_invoke_with_retry_eventually_succeeds(self) -> None:
        attempts = {'count': 0}

        def flaky():
            attempts['count'] += 1
            if attempts['count'] < 3:
                raise ValueError('temporary failure')
            return 'ok'

        result = invoke_with_retry(flaky, retries=2, backoff_seconds=0)

        self.assertEqual(result, 'ok')
        self.assertEqual(attempts['count'], 3)

    def test_invoke_with_retry_raises_after_exhaustion(self) -> None:
        with patch('time.sleep', return_value=None):
            with self.assertRaises(RuntimeError):
                invoke_with_retry(lambda: (_ for _ in ()).throw(RuntimeError('still failing')), retries=1, backoff_seconds=0)


if __name__ == '__main__':
    unittest.main()
