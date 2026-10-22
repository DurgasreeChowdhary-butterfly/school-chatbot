"""Chat sessions, stored in SQLite (table chat_sessions) so a server restart does not lose them.
A session holds the visible conversation, consent, the enquiry waiting for confirmation and the failed
ticket lookups. Each request loads its session with get_session() and stores it again with save().
Sessions idle for 2 hours are deleted (they can contain names and mobile numbers)."""
import json
import time
from collections import deque
from dataclasses import dataclass, field

from . import config, db
from .llm.base import Message

IDLE_SECONDS = 2 * 60 * 60  # forget sessions idle for 2 hours


@dataclass
class Session:
    id: str
    history: deque = field(default_factory=lambda: deque(maxlen=config.HISTORY_LIMIT))
    last_seen: float = field(default_factory=time.time)
    turn: int = 0  # counts the visitor's messages
    # Enquiry details checked by submit_enquiry, waiting for the visitor to confirm: {"details", "turn"}.
    pending_enquiry: dict | None = None
    failed_lookups: int = 0  # wrong ticket reference/mobile pairs in this session
    consent_at: str | None = None  # when the visitor tapped "I agree" on the privacy notice


def get_session(session_id: str) -> Session:
    """The stored session, or a new one. Call save() after changing it."""
    _forget_idle()
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        return Session(id=session_id)
    # Only the visible text of each message is stored, never the AI's tool steps.
    history = [Message(role=m["role"], content=m["content"]) for m in json.loads(row["history"])]
    return Session(
        id=session_id,
        history=deque(history, maxlen=config.HISTORY_LIMIT),
        turn=row["turn"],
        pending_enquiry=json.loads(row["pending_enquiry"]) if row["pending_enquiry"] else None,
        failed_lookups=row["failed_lookups"],
        consent_at=row["consent_at"],
    )


def save(session: Session) -> None:
    session.last_seen = time.time()
    history = json.dumps([{"role": m.role, "content": m.content} for m in session.history], ensure_ascii=False)
    pending = json.dumps(session.pending_enquiry) if session.pending_enquiry else None
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO chat_sessions (id, history, turn, pending_enquiry, failed_lookups, consent_at, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET history = excluded.history, turn = excluded.turn,
                   pending_enquiry = excluded.pending_enquiry, failed_lookups = excluded.failed_lookups,
                   consent_at = excluded.consent_at, last_seen = excluded.last_seen""",
            (session.id, history, session.turn, pending, session.failed_lookups, session.consent_at,
             session.last_seen),
        )


def remember(session: Session, *messages: Message) -> None:
    session.history.extend(messages)


def clear_all() -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM chat_sessions")


def _forget_idle() -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM chat_sessions WHERE last_seen < ?", (time.time() - IDLE_SECONDS,))
