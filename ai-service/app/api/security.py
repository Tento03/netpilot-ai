"""Internal token check. The token comes from INTERNAL_TOKEN; if it is empty, every call is refused."""
from __future__ import annotations

import hmac
import os

MAX_QUESTION_LEN = 500


def token_ok(provided: str | None, expected: str | None = None) -> bool:
    expected = os.environ.get("INTERNAL_TOKEN", "") if expected is None else expected
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))