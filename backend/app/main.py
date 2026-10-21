"""School chatbot backend. Start with: uvicorn backend.app.main:app --reload"""
import json
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, db, jobs, sessions
from .chat_service import FALLBACK_REPLY, handle_message
from .knowledge import KB_DIR, load_all_campuses
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """On start: create the database and start the reminder job. On stop: stop the job."""
    db.init_db()
    stop = threading.Event()
    jobs.start_background_job(stop)
    yield
    stop.set()


app = FastAPI(title="School Chatbot", lifespan=lifespan)

# The chat window files (chat.js, chat.css) and a test page that embeds them.
WIDGET_DIR = KB_DIR.parent / "widget"
app.mount("/widget", StaticFiles(directory=WIDGET_DIR), name="widget")

# School name, campuses and menus for the chat window (from kb/school.json).
SCHOOL = json.loads((KB_DIR / "school.json").read_text(encoding="utf-8"))


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


@app.get("/demo", include_in_schema=False)
def demo_page():
    """A pretend school web page with the chat window, for testing."""
    return FileResponse(WIDGET_DIR / "demo.html")


@app.get("/config")
def widget_config():
    """What the chat window needs to show its opening flow."""
    campuses = [c for c in SCHOOL["campuses"] if c["id"] in KNOWLEDGE]
    return {
        "demo": config.DEMO_MODE,
        "school_name": SCHOOL["school_name"],
        "assistant_name": SCHOOL["assistant_name"],
        "campuses": campuses,
        "menus": SCHOOL["menus"],
    }


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
