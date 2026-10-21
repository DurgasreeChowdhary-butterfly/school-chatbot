"""School chatbot backend. Start with: uvicorn backend.app.main:app --reload"""
import json
import logging
import threading
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StringConstraints

from . import config, db, jobs, sessions, staff
from .chat_service import FALLBACK_REPLY, handle_message
from .knowledge import KB_DIR, load_all_campuses
from .llm.base import LLMProvider
from .llm.factory import get_provider
from .logs import setup_logging
from .ratelimit import RateLimiter

setup_logging()
log = logging.getLogger("chatbot")

# Loaded once at startup: {campus folder name: knowledge text}.
KNOWLEDGE = load_all_campuses()
log.info("Loaded knowledge for campuses: %s", ", ".join(KNOWLEDGE) or "none")

TOO_FAST_REPLY = "You're sending messages too quickly. Please wait a minute and try again."
session_limiter = RateLimiter(config.CHAT_LIMIT_PER_SESSION, 60)
ip_limiter = RateLimiter(config.CHAT_LIMIT_PER_IP, 60)

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
    setup_logging()  # again, now that uvicorn's own log handlers exist
    db.init_db()
    stop = threading.Event()
    jobs.start_background_job(stop)
    yield
    stop.set()


app = FastAPI(title="School Chatbot", lifespan=lifespan)
app.include_router(staff.router)

# Other websites may call the chat only if listed in ALLOWED_ORIGINS.
if config.ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.ALLOWED_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

# The chat window files (chat.js, chat.css) and a test page that embeds them.
WIDGET_DIR = KB_DIR.parent / "widget"
app.mount("/widget", StaticFiles(directory=WIDGET_DIR), name="widget")

# School name, campuses and menus for the chat window (from kb/school.json).
SCHOOL = json.loads((KB_DIR / "school.json").read_text(encoding="utf-8"))


def privacy_notice(campus: str) -> str:
    """The campus privacy notice as plain text (headings and the DUMMY note left out)."""
    path = KB_DIR / campus / "privacy_notice.md"
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if line.strip() and not line.lstrip().startswith(("#", ">")))


# ---------- Requests and replies ----------

SessionId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{16,100}$")]
CampusId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{1,50}$")]
MessageText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=config.MAX_MESSAGE_CHARS)]


class ChatRequest(BaseModel):
    session_id: SessionId
    campus: CampusId = "pilot-campus"
    message: MessageText
    group: Annotated[str, StringConstraints(max_length=40)] | None = None


class ChatResponse(BaseModel):
    reply: str
    demo: bool
    action: str | None = None   # "consent": the chat window shows the privacy notice and an "I agree" button
    notice: str | None = None   # the privacy notice text, sent with action "consent"


class ConsentRequest(BaseModel):
    session_id: SessionId
    agree: bool


@app.exception_handler(RequestValidationError)
async def friendly_validation_error(request: Request, exc: RequestValidationError):
    """Bad chat requests get a friendly reply the chat window can show, never a stack trace."""
    if request.url.path not in ("/chat", "/consent"):
        return JSONResponse({"detail": exc.errors()}, status_code=422)
    fields = {str(e["loc"][-1]) for e in exc.errors()}
    if "message" in fields:
        too_long = any(e["type"] == "string_too_long" for e in exc.errors())
        reply = (f"Your message is too long. Please keep it under {config.MAX_MESSAGE_CHARS} characters."
                 if too_long else "Please type a message.")
    else:
        reply = "Sorry, I couldn't read that request. Please refresh the page and try again."
    return JSONResponse({"reply": reply, "demo": config.DEMO_MODE}, status_code=422)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _too_fast(request: Request, session_id: str) -> JSONResponse | None:
    if not ip_limiter.allow(_client_ip(request)) or not session_limiter.allow(session_id):
        log.warning("Rate limit hit for a chat session")
        return JSONResponse({"reply": TOO_FAST_REPLY, "demo": config.DEMO_MODE}, status_code=429)
    return None


# ---------- Routes ----------

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


@app.post("/consent")
def consent(req: ConsentRequest, request: Request):
    """The visitor tapped "I agree" (or "No thanks") on the privacy notice."""
    if blocked := _too_fast(request, req.session_id):
        return blocked
    session = sessions.get_session(req.session_id)
    session.consent_at = db.now() if req.agree else None
    return {"ok": True, "consent": req.agree}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request):
    if blocked := _too_fast(request, req.session_id):
        return blocked
    knowledge = KNOWLEDGE.get(req.campus)
    if knowledge is None:
        return ChatResponse(reply="Sorry, I don't have information for that campus yet.", demo=config.DEMO_MODE)

    session = sessions.get_session(req.session_id)
    try:
        p = provider()
    except Exception:
        log.exception("Could not create the AI provider")
        return ChatResponse(reply=FALLBACK_REPLY, demo=config.DEMO_MODE)

    outcome = handle_message(p, session, req.campus, knowledge, req.message, req.group)
    notice = privacy_notice(req.campus) if outcome.action == "consent" else None
    return ChatResponse(reply=outcome.reply, demo=config.DEMO_MODE, action=outcome.action, notice=notice)
