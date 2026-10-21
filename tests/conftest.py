"""Shared test setup. Tests always use the FakeLLM, never the live model."""
import os

# Set before the app is imported, so .env values (like the real provider) are not used.
os.environ["LLM_PROVIDER"] = "fake"
os.environ["DEMO_MODE"] = "true"

import pytest
from fastapi.testclient import TestClient

from backend.app import main, sessions
from backend.app.llm.fake_provider import FakeLLM


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


def chat(client, message, session_id="test-session", **extra):
    """Send one chat message and return the JSON reply."""
    r = client.post("/chat", json={"session_id": session_id, "message": message, **extra})
    assert r.status_code == 200, r.text
    return r.json()
