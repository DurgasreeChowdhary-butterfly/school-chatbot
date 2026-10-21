"""Chat sessions kept in memory (they are lost when the server restarts, which is fine for the pilot)."""
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from . import config
from .llm.base import Message

IDLE_SECONDS = 2 * 60 * 60  # forget sessions idle for 2 hours


@dataclass
class Session:
    id: str
    history: deque = field(default_factory=lambda: deque(maxlen=config.HISTORY_LIMIT))
    last_seen: float = field(default_factory=time.time)
    turn: int = 0  # counts the visitor's messages


_sessions: dict[str, Session] = {}
_lock = threading.Lock()


def get_session(session_id: str) -> Session:
    with _lock:
        _forget_idle()
        session = _sessions.get(session_id)
        if session is None:
            session = _sessions[session_id] = Session(id=session_id)
        session.last_seen = time.time()
        return session


def remember(session: Session, *messages: Message) -> None:
    session.history.extend(messages)


def clear_all() -> None:
    with _lock:
        _sessions.clear()


def _forget_idle() -> None:
    cutoff = time.time() - IDLE_SECONDS
    for sid in [sid for sid, s in _sessions.items() if s.last_seen < cutoff]:
        del _sessions[sid]
