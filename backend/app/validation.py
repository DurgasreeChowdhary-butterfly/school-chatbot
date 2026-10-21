"""Checks for details people type in. The backend never trusts the AI to have checked them."""
import re

MOBILE = re.compile(r"^[6-9]\d{9}$")


def normalize_mobile(value: str) -> str | None:
    """Return a valid 10-digit Indian mobile number, or None.
    Accepts spaces, dashes, brackets and a +91, 91 or 0 in front."""
    digits = re.sub(r"[\s\-().]", "", str(value or ""))
    if digits.startswith("+91"):
        digits = digits[3:]
    elif len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if MOBILE.match(digits) else None


def mask_mobile(value: str) -> str:
    """For logs: 9876543210 -> 98******10."""
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[:2] + "*" * max(len(digits) - 4, 0) + digits[-2:] if len(digits) >= 6 else "***"


def clean_name(value: str) -> str | None:
    """A person's name: 2 to 80 characters, letters, spaces and . ' - only."""
    name = " ".join(str(value or "").split())
    if not 2 <= len(name) <= 80:
        return None
    if not all(ch.isalpha() or ch in " .'-" for ch in name):
        return None
    return name


def clean_text(value: str, max_len: int, required: bool = False) -> str | None:
    """Free text, trimmed. None means invalid (missing when required, or too long)."""
    text = " ".join(str(value or "").split())
    if required and len(text) < 2:
        return None
    return text if len(text) <= max_len else None


def match_choice(value: str, choices: list[str]) -> str | None:
    """Case-insensitive match against a fixed list, e.g. classes or categories."""
    wanted = " ".join(str(value or "").split()).lower()
    for choice in choices:
        if choice.lower() == wanted:
            return choice
    return None
