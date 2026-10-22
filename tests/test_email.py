"""Real email through SMTP, tested with a fake SMTP server: TEST_MODE redirect, never to example.com,
sent/failed marks, retries, the staff resend button and urgent emails first."""
from datetime import datetime, timedelta

import pytest

from backend.app import db, notify, routing
from tests.conftest import tool_turn
from tests.fake_smtp import FakeSMTPServer
from tests.test_staff import HEADERS, login

COUNSELLOR = {"role": "Admission counsellor", "email": "admissions.campusa@example.com"}
REAL_LOOKING = {"role": "Admission counsellor", "email": "counsellor@school-pilot.in"}


@pytest.fixture
def smtp(monkeypatch):
    server = FakeSMTPServer()
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", str(server.port))
    monkeypatch.setenv("SMTP_SECURITY", "none")
    monkeypatch.setenv("SMTP_USER", "")
    monkeypatch.setenv("TEST_MODE", "true")
    monkeypatch.setenv("TEST_RECIPIENT", "tester@school-pilot.in")
    monkeypatch.setattr(notify, "SEND_IN_BACKGROUND", False)
    yield server
    server.stop()


def outbox_row():
    [row] = db.list_rows("outbox")
    return row


def test_test_mode_sends_every_email_to_the_test_recipient(smtp):
    notify.notify("pilot-campus", COUNSELLOR, "New enquiry E-1001", "Body text", "E-1001", "enquiry")
    [mail] = smtp.messages
    assert mail["to"] == ["tester@school-pilot.in"]
    assert "Admission counsellor <admissions.campusa@example.com>" in mail["subject"]
    assert "New enquiry E-1001" in mail["subject"] and mail["body"].strip() == "Body text"
    row = outbox_row()
    assert row["status"] == "sent" and row["sent_to"] == "tester@school-pilot.in" and row["attempts"] == 1


def test_never_sends_to_example_com(smtp, monkeypatch):
    monkeypatch.setenv("TEST_MODE", "false")
    notify.notify("pilot-campus", COUNSELLOR, "Subject", "Body", "E-1001", "enquiry")
    assert smtp.messages == []
    row = outbox_row()
    assert row["status"] == "blocked" and "placeholder" in row["error"]


def test_example_com_test_recipient_is_blocked_too(smtp, monkeypatch):
    monkeypatch.setenv("TEST_RECIPIENT", "me@example.com")
    notify.notify("pilot-campus", REAL_LOOKING, "Subject", "Body", "E-1001", "enquiry")
    assert smtp.messages == [] and outbox_row()["status"] == "blocked"


def test_test_mode_without_recipient_sends_nothing(smtp, monkeypatch):
    monkeypatch.setenv("TEST_RECIPIENT", "")
    notify.notify("pilot-campus", REAL_LOOKING, "Subject", "Body", "E-1001", "enquiry")
    assert smtp.messages == []
    assert outbox_row()["status"] == "blocked" and "TEST_RECIPIENT" in outbox_row()["error"]


def test_real_address_used_when_test_mode_is_off(smtp, monkeypatch):
    monkeypatch.setenv("TEST_MODE", "false")
    notify.notify("pilot-campus", REAL_LOOKING, "New enquiry", "Body", "E-1001", "enquiry")
    assert smtp.messages[0]["to"] == ["counsellor@school-pilot.in"]
    assert smtp.messages[0]["subject"] == "New enquiry"


def test_failed_email_is_retried_later(smtp):
    smtp.fail_next = 1
    notify.notify("pilot-campus", REAL_LOOKING, "Subject", "Body", "E-1001", "enquiry")
    row = outbox_row()
    assert row["status"] == "failed" and row["attempts"] == 1 and "451" in row["error"]
    assert notify.send_due() == 0  # not due yet
    assert notify.send_due(datetime.now() + timedelta(minutes=2)) == 1
    row = outbox_row()
    assert row["status"] == "sent" and row["attempts"] == 2 and row["error"] == ""


def test_retries_stop_after_max_attempts(smtp):
    smtp.fail_next = 100
    notify.notify("pilot-campus", REAL_LOOKING, "Subject", "Body", "E-1001", "enquiry")
    later = datetime.now()
    for _ in range(10):
        later += timedelta(hours=2)
        notify.send_due(later)
    row = outbox_row()
    assert row["status"] == "failed" and row["attempts"] == notify.MAX_ATTEMPTS


def test_server_down_marks_failed(smtp, monkeypatch):
    monkeypatch.setenv("SMTP_PORT", "1")  # nothing listens there
    notify.notify("pilot-campus", REAL_LOOKING, "Subject", "Body", "E-1001", "enquiry")
    assert outbox_row()["status"] == "failed"


def test_staff_can_resend_a_failed_email(client, smtp):
    smtp.fail_next = 100
    notify.notify("pilot-campus", REAL_LOOKING, "Subject", "Body", "E-1001", "enquiry")
    smtp.fail_next = 0
    login(client)
    row = outbox_row()
    assert client.post("/staff/api/resend", json={"id": row["id"]}).status_code == 403  # header missing
    r = client.post("/staff/api/resend", json={"id": row["id"]}, headers=HEADERS)
    assert r.status_code == 200 and r.json()["status"] == "sent"
    assert len(smtp.messages) == 1 and outbox_row()["status"] == "sent"
    assert client.post("/staff/api/resend", json={"id": 999}, headers=HEADERS).status_code == 404


def test_resend_needs_login_and_email_settings(client, monkeypatch):
    assert client.post("/staff/api/resend", json={"id": 1}, headers=HEADERS).status_code == 401
    login(client)
    assert client.post("/staff/api/resend", json={"id": 1}, headers=HEADERS).status_code == 400  # no SMTP_HOST


def test_urgent_safety_emails_are_sent_first(client, fake, smtp, monkeypatch):
    # Emails pile up (as if the mail server was busy), then are all sent in one go.
    monkeypatch.setattr(notify, "_start_sending", lambda: None)
    notify.notify("pilot-campus", REAL_LOOKING, "Older routine email", "Body", "E-1001", "enquiry")
    tool_turn(client, fake, "My child is being bullied",
              ("create_ticket", {"category": "Safety, health, bullying", "description": "Bullied at break",
                                 "parent_name": "Sample Parent", "mobile": "9876543210"}))
    notify.notify("pilot-campus", REAL_LOOKING, "Newer routine email", "Body", "E-1002", "enquiry")
    notify.send_due()
    subjects = [m["subject"] for m in smtp.messages]
    assert len(subjects) == 5
    assert all("URGENT" in s for s in subjects[:3])
    assert "Older routine email" in subjects[3] and "Newer routine email" in subjects[4]


def test_no_smtp_settings_only_logs(fake):
    notify.notify("pilot-campus", REAL_LOOKING, "Subject", "Body", "E-1001", "enquiry")
    assert outbox_row()["status"] == "logged" and notify.send_due() == 0


def test_old_database_gets_the_new_outbox_columns(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, campus TEXT NOT NULL, "
                     "to_role TEXT NOT NULL, to_email TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL, "
                     "related_ref TEXT DEFAULT '', kind TEXT NOT NULL, status TEXT NOT NULL, "
                     "created_at TEXT NOT NULL, error TEXT DEFAULT '')")
    db.init_db(path)
    with db.connect() as conn:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(outbox)")}
    assert {"priority", "attempts", "next_try_at", "sent_at", "sent_to"} <= columns


def test_counsellor_override_still_applies(monkeypatch):
    monkeypatch.setenv("COUNSELLOR_EMAIL_PILOT", "counsellor@school-pilot.in")
    assert routing.counsellor("pilot-campus")["email"] == "counsellor@school-pilot.in"
