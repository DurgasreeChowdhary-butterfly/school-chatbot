"""Shared test setup. Tests always use the FakeLLM, never the live model."""
import json
import os

# Set before the app is imported, so .env values (like the real provider) are not used.
os.environ["LLM_PROVIDER"] = "fake"
os.environ["DEMO_MODE"] = "true"
os.environ["ADMIN_PASSWORD"] = "test-password"

import pytest
from fastapi.testclient import TestClient

from backend.app import db, main, sessions, staff
from backend.app.llm.base import LLMResult, ToolCall
from backend.app.llm.fake_provider import FakeLLM


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    """Every test gets its own empty database and no staff logins."""
    db.init_db(tmp_path / "test.db")
    staff.reset_state()
    main.session_limiter.reset()
    main.ip_limiter.reset()


@pytest.fixture
def fake():
    """A fresh FakeLLM plugged into the app, with empty sessions."""
    f = FakeLLM()
    main.set_provider(f)
    sessions.clear_all()
    yield f


@pytest.fixture
def client(fake):
    return TestClient(main.app)


def sid(name: str) -> str:
    """Session ids must be 16+ characters; tests use short names like "s1"."""
    return f"{name}-0123456789abcdef"


def chat(client, message, session_id="test-session", **extra):
    """Send one chat message and return the JSON reply."""
    r = client.post("/chat", json={"session_id": sid(session_id), "message": message, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def agree(client, session_id="s1"):
    """The visitor taps "I agree" on the privacy notice."""
    assert client.post("/consent", json={"session_id": sid(session_id), "agree": True}).status_code == 200


def tool_turn(client, fake, message, *calls, reply="OK", session_id="s1", consent=True):
    """One visitor message where the AI calls the given tools (name, args), then replies.
    Returns the tool results the backend sent back to the AI. By default the visitor has agreed to the privacy notice."""
    if consent:
        agree(client, session_id)
    fake.add(LLMResult(tool_calls=[ToolCall(name=n, arguments=a, id=f"c{i}") for i, (n, a) in enumerate(calls)]),
             LLMResult(text=reply))
    chat(client, message, session_id=session_id)
    sent = fake.calls[-1]["messages"]
    return [json.loads(m.content) for m in sent if m.role == "tool"][-len(calls):]
