"""All settings from .env in one place. Other files import from here."""
import os
import re

from dotenv import load_dotenv

# Read the .env file in the project folder (values already set in the environment win).
load_dotenv()


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    return default if not value else value in ("1", "true", "yes")


def _int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    return int(value) if value else default


def _list(name: str) -> list[str]:
    return [item.strip().rstrip("/") for item in os.getenv(name, "").split(",") if item.strip()]


# DEMO_MODE=true means kb/ holds dummy content. Defaults to true to stay safe.
DEMO_MODE = _bool("DEMO_MODE", True)

# How many recent messages the bot remembers per chat session.
# 20 (not 12) so a whole enquiry conversation fits, from first detail to confirmation.
HISTORY_LIMIT = _int("HISTORY_LIMIT", 20)

# Longest message a visitor may send, in characters.
MAX_MESSAGE_CHARS = 1000

# Chat messages allowed per minute, per chat session and per IP address.
CHAT_LIMIT_PER_SESSION = _int("CHAT_LIMIT_PER_SESSION", 12)
CHAT_LIMIT_PER_IP = _int("CHAT_LIMIT_PER_IP", 40)

# Websites allowed to embed the chat window from another address, e.g. https://www.school.example
# Empty means only pages served by this server (like /demo) can use the chat.
# Mistakes found in the settings, logged when the server starts.
WARNINGS: list[str] = []


def _origins(name: str) -> list[str]:
    """Only exact website addresses like https://www.school.example: "*" (every website) and addresses with a path
    are refused, so the chat can never be opened up to every website by accident."""
    kept = []
    for origin in _list(name):
        if re.fullmatch(r"https?://[A-Za-z0-9.-]+(:\d+)?", origin):
            kept.append(origin)
            if origin.startswith("http://") and not re.fullmatch(r"http://(localhost|127\.0\.0\.1)(:\d+)?", origin):
                WARNINGS.append(f"{name}: {origin} uses http, not https")
        else:
            WARNINGS.append(f"{name}: '{origin}' ignored (use exact addresses like https://www.school.example, never *)")
    return kept


ALLOWED_ORIGINS = _origins("ALLOWED_ORIGINS")

# Months to keep enquiries, tickets, callbacks, emails and chats (scripts/purge_old_records.py deletes older ones;
# anything still being followed up is kept). The privacy notice must say the same.
RETENTION_MONTHS = _int("RETENTION_MONTHS", 12)

# /docs and /openapi.json (the automatic API pages): on while testing, off when the real content is live.
API_DOCS = _bool("API_DOCS", DEMO_MODE)
