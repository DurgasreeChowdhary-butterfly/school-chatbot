"""School chatbot backend. Start with: uvicorn backend.app.main:app --reload"""
import logging
import os
from collections import defaultdict, deque
from datetime import date

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field

from .knowledge import load_all_campuses
from .llm.base import LLMProvider, Message
from .llm.factory import get_provider
from .prompts import build_system_prompt

# Read settings from the .env file in the project folder.
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("chatbot")

# DEMO_MODE=true means kb/ holds dummy content. Defaults to true to stay safe.
DEMO_MODE = os.getenv("DEMO_MODE", "true").strip().lower() == "true"

FALLBACK_REPLY = "I'm having trouble right now. Please call the front office."
HISTORY_LIMIT = 12

# Loaded once at startup: {campus folder name: knowledge text}.
KNOWLEDGE = load_all_campuses()
log.info("Loaded knowledge for campuses: %s", ", ".join(KNOWLEDGE) or "none")

# Last 12 messages per session_id, kept in memory (cleared when the server restarts).
HISTORY: dict[str, deque[Message]] = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))

_provider: LLMProvider | None = None


def provider() -> LLMProvider:
    """Create the provider on first use, so a missing key shows up as a logged error, not a crash."""
    global _provider
    if _provider is None:
        _provider = get_provider()
    return _provider


app = FastAPI(title="School Chatbot")


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    campus: str = "pilot-campus"
    message: str = Field(min_length=1, max_length=1000)


class ChatResponse(BaseModel):
    reply: str
    demo: bool


@app.get("/health")
def health():
    """Quick check that the server is running."""
    return {"status": "ok", "demo": DEMO_MODE}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    knowledge = KNOWLEDGE.get(req.campus)
    if knowledge is None:
        return ChatResponse(reply="Sorry, I don't have information for that campus yet.", demo=DEMO_MODE)

    history = HISTORY[req.session_id]
    user_message = Message(role="user", content=req.message.strip())
    system_prompt = build_system_prompt(knowledge, date.today().strftime("%d %B %Y"))

    try:
        result = provider().generate(system_prompt, [*history, user_message])
    except Exception:
        log.exception("Provider error")
        return ChatResponse(reply=FALLBACK_REPLY, demo=DEMO_MODE)

    if result.failed or not result.text:
        log.error("Provider failed: %s", result.error or "empty reply")
        return ChatResponse(reply=FALLBACK_REPLY, demo=DEMO_MODE)

    history.append(user_message)
    history.append(Message(role="assistant", content=result.text))
    return ChatResponse(reply=result.text, demo=DEMO_MODE)
