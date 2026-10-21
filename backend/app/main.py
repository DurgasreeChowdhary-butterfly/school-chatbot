"""School chatbot backend. Start with: uvicorn backend.app.main:app --reload"""
import logging

from fastapi import FastAPI
from pydantic import BaseModel, Field

from . import config, sessions
from .chat_service import FALLBACK_REPLY, handle_message
from .knowledge import load_all_campuses
from .llm.base import LLMProvider
from .llm.factory import get_provider

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("chatbot")

# Loaded once at startup: {campus folder name: knowledge text}.
KNOWLEDGE = load_all_campuses()
log.info("Loaded knowledge for campuses: %s", ", ".join(KNOWLEDGE) or "none")

_provider: LLMProvider | None = None


def provider() -> LLMProvider:
    """Create the provider on first use, so a missing key shows up as a logged error, not a crash."""
    global _provider
    if _provider is None:
        _provider = get_provider()
    return _provider


def set_provider(p: LLMProvider) -> None:
    """Used by tests to plug in the FakeLLM."""
    global _provider
    _provider = p


app = FastAPI(title="School Chatbot")


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    campus: str = "pilot-campus"
    message: str = Field(min_length=1, max_length=config.MAX_MESSAGE_CHARS)
    group: str | None = Field(default=None, max_length=40)


class ChatResponse(BaseModel):
    reply: str
    demo: bool


@app.get("/health")
def health():
    """Quick check that the server is running."""
    return {"status": "ok", "demo": config.DEMO_MODE}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    knowledge = KNOWLEDGE.get(req.campus)
    if knowledge is None:
        return ChatResponse(reply="Sorry, I don't have information for that campus yet.", demo=config.DEMO_MODE)

    session = sessions.get_session(req.session_id)
    try:
        p = provider()
    except Exception:
        log.exception("Could not create the AI provider")
        return ChatResponse(reply=FALLBACK_REPLY, demo=config.DEMO_MODE)

    outcome = handle_message(p, session, req.campus, knowledge, req.message.strip(), req.group)
    return ChatResponse(reply=outcome.reply, demo=config.DEMO_MODE)
