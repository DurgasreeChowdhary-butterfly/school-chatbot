"""Checks for details people type in. The backend never trusts the AI to have checked them."""
import re
from difflib import SequenceMatcher

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


# ---------- Did the person actually give this detail? ----------
# The AI must never make up a detail (seen in the simulated-user test: a visit time saved that was never asked for).
# Every detail it passes to a saving tool must appear in what the person typed in this chat.

FILLER = {"for", "now", "the", "and", "any", "time", "day", "on", "at", "in", "to", "of", "an", "or", "is", "am", "pm",
          "please", "prefer", "preferred", "preference", "visit", "around", "about", "my", "mr", "mrs", "ms", "dr"}
NO_VISIT = re.compile(r"\b(no visit|not now|later|not yet|none)\b", re.I)
SAID_NO = re.compile(r"\b(no|not|later|skip|don'?t|nahi|ledu|vaddu|none|nothing)\b", re.I)
NUMBER_WORDS = {n: rf"\b({a}|{b})\b" for n, a, b in [
    (1, "one", "first"), (2, "two", "second"), (3, "three", "third"), (4, "four", "fourth"), (5, "five", "fifth"),
    (6, "six", "sixth"), (7, "seven", "seventh"), (8, "eight", "eighth"), (9, "nine", "ninth"), (10, "ten", "tenth")]}
EMPTY_ANSWERS = {"", "none", "no", "nil", "n/a", "na", "-", "not specified", "not given", "not provided", "skipped"}


def said_by_person(value: str, said: str, kind: str = "text") -> bool:
    """True if `value` appears in `said` (all the person's messages in this chat), allowing for small changes:
    names and text need one of their words, a mobile its 10 digits, a class its number or name,
    and "no visit for now" needs the person to have said no / not now / later."""
    value, said_low = str(value or "").strip(), str(said or "").lower()
    if kind == "mobile":
        return normalize_mobile(value) is not None and normalize_mobile(value) in re.sub(r"\D", "", said_low)
    if kind == "class":
        keys = re.findall(r"\d+|nursery|lkg|ukg", value.lower())
        for k in keys:
            if re.search(rf"(?<!\d){k}(?!\d)" if k.isdigit() else rf"\b{k}\b", said_low):
                return True
            if k.isdigit() and int(k) in NUMBER_WORDS and re.search(NUMBER_WORDS[int(k)], said_low):
                return True  # "third standard", "class three"
        return False
    if kind == "visit" and NO_VISIT.search(value):
        return bool(SAID_NO.search(said_low))
    words = [w for w in re.findall(r"[a-z0-9]+", value.lower()) if w not in FILLER and (len(w) > 1 or w.isdigit())]
    typed = set(re.findall(r"[a-z0-9]+", said_low))
    return any(re.search(rf"\b{re.escape(w)}", said_low) or _close_to_any(w, typed) for w in words)


def _close_to_any(word: str, typed: set[str]) -> bool:
    """A small spelling difference is fine: the AI may write "Saturday morning" for "satrday mornig"."""
    if len(word) < 4 or word.isdigit():
        return False
    return any(len(t) >= 4 and SequenceMatcher(None, word, t).ratio() >= 0.75 for t in typed)


def made_up(details: dict[str, tuple[str, str]], said: str) -> dict[str, str]:
    """{field: problem} for details the person never gave. `details` maps field -> (value, kind)."""
    problems = {}
    for field, (value, kind) in details.items():
        if kind == "optional":
            if str(value or "").strip().lower() in EMPTY_ANSWERS:
                continue
            kind = "text"
        if not said_by_person(value, said, kind):
            problems[field] = ("This does not match anything the person typed in the chat. If they gave it, pass it "
                               "exactly as they typed it. If they did not, ask them for it; never fill in or assume a "
                               "detail.")
    return problems
