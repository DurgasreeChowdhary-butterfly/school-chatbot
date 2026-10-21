"""All settings from .env in one place. Other files import from here."""
import os

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
ALLOWED_ORIGINS = _list("ALLOWED_ORIGINS")
