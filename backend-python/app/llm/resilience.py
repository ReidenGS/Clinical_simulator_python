from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar


T = TypeVar('T')


def invoke_with_retry(operation: Callable[[], T], retries: int = 2, backoff_seconds: float = 0.5) -> T:
    last_error: Exception | None = None
    attempts = max(1, retries + 1)

    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:  # pragma: no cover - exercised via callers/tests
            last_error = exc
            if attempt == attempts - 1:
                break
            sleep_for = backoff_seconds * (attempt + 1)
            if sleep_for > 0:
                time.sleep(sleep_for)

    if last_error is not None:
        raise last_error
    raise RuntimeError('invoke_with_retry reached an unexpected state')
