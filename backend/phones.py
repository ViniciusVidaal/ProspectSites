from __future__ import annotations

import re


def normalize_phone(value: str) -> str:
    """Return a stable DDI + DDD + number key for Firestore lookups."""
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) in (10, 11):
        digits = f"55{digits}"
    return digits[:15]
