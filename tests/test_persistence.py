"""Chat sessions, consent and half-finished enquiries survive a server restart (they are stored in SQLite)."""
import importlib
import time

from fastapi.testclient import TestClient

from backend.app import db, main, sessions
from tests.conftest import agree, chat, sid, tool_turn

DETAILS = {"parent_name": "Sample Parent", "child_name": "Sample Child", "class_applying": "Grade 3",
           "mobile": "9876543210", "visit_preference": "Saturday morning"}


def restart(client: TestClient) -> TestClient:
    """Stop the app and start it again on the same database: anything kept only in memory is gone."""
    client.__exit__(None, None, None)
    importlib.reload(sessions)
    main.session_limiter.reset()
    main.ip_limiter.reset()
    new_client = TestClient(main.app)
    new_client.__enter__()
    return new_client


def test_conversation_survives_a_restart(client, fake):
    client.__enter__()
    chat(client, "What is the fee for Grade 3?", session_id="p1")
    client = restart(client)
    chat(client, "And for Grade 6?", session_id="p1")
    assert [m.content for m in fake.calls[-1]["messages"]] == [
        "What is the fee for Grade 3?", "This is a scripted test reply.", "And for Grade 6?"]
    client.__exit__(None, None, None)


def test_consent_survives_a_restart(client, fake):
    client.__enter__()
    agree(client, "p2")
    client = restart(client)
    [result] = tool_turn(client, fake, "Please call me", ("request_callback", {"name": "Sample Parent",
                         "mobile": "9876543210"}), session_id="p2", consent=False)
    assert result["status"] == "created"
    assert db.list_rows("callbacks")[0]["consent_at"]
    client.__exit__(None, None, None)


def test_pending_enquiry_can_be_confirmed_after_a_restart(client, fake):
    client.__enter__()
    [checked] = tool_turn(client, fake, "Here are my details", ("submit_enquiry", DETAILS), session_id="p3")
    assert checked["status"] == "needs_confirmation"
    client = restart(client)
    [saved] = tool_turn(client, fake, "Yes", ("confirm_enquiry", {}), session_id="p3", consent=False)
    assert saved["status"] == "saved" and saved["ref"] == "E-1001"
    assert db.list_rows("enquiries")[0]["child_name"] == "Sample Child"
    client.__exit__(None, None, None)


def test_confirmation_rule_still_holds_after_a_restart(client, fake):
    """A restart must not let the AI confirm in the same turn as the summary."""
    client.__enter__()
    [_, refused] = tool_turn(client, fake, "details", ("submit_enquiry", DETAILS), ("confirm_enquiry", {}),
                             session_id="p4")
    assert "not confirmed" in refused["error"]
    client = restart(client)
    assert db.list_rows("enquiries") == []
    client.__exit__(None, None, None)


def test_failed_lookups_survive_a_restart(client, fake):
    """Restarting must not reset the limit on guessing ticket numbers."""
    client.__enter__()
    for _ in range(5):
        tool_turn(client, fake, "status", ("get_ticket_status", {"ticket_ref": "T-1001", "mobile": "9876543210"}),
                  session_id="p5", consent=False)
    client = restart(client)
    [result] = tool_turn(client, fake, "status", ("get_ticket_status", {"ticket_ref": "T-1001", "mobile": "9876543210"}),
                         session_id="p5", consent=False)
    assert "Too many attempts" in result["error"]
    client.__exit__(None, None, None)


def test_idle_sessions_are_deleted(client, fake, monkeypatch):
    chat(client, "Hello", session_id="old")
    monkeypatch.setattr(time, "time", lambda: 10 ** 12)  # far in the future
    sessions.get_session(sid("someone-else"))
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0] == 0
