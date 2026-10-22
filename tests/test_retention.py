"""Data retention: purge of old records (never open ones) and deleting one person's data on request."""
import importlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from backend.app import config, db, retention, sessions
from backend.app.llm.base import Message
from tests.test_staff import HEADERS, login

ROOT = Path(__file__).resolve().parents[1]
OLD = (datetime.now() - timedelta(days=400)).isoformat(timespec="seconds")   # 13 months ago
RECENT = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")


def enquiry(mobile="9876543210", status="Closed", when=OLD, name="Sample Parent"):
    row = db.insert("enquiries", {"campus": "pilot-campus", "parent_name": name, "child_name": "Sample Kid",
                                  "class_applying": "Grade 3", "mobile": mobile, "visit_preference": "Saturday",
                                  "assigned_to": "Admission counsellor"})
    db.update("enquiries", row["ref"], status=status)
    _age("enquiries", row["ref"], when)
    return row["ref"]


def ticket(mobile="9876543210", status="Resolved", when=OLD):
    row = db.insert("tickets", {"campus": "pilot-campus", "category": "Transport", "description": "Bus late",
                                "parent_name": "Sample Parent", "mobile": mobile, "urgent": 0,
                                "first_contact": "Transport coordinator", "backup_contact": "Principal"})
    db.update("tickets", row["ref"], status=status)
    _age("tickets", row["ref"], when)
    return row["ref"]


def email(ref, when=OLD, body="Body"):
    row = db.add_outbox({"campus": "pilot-campus", "to_role": "Principal", "to_email": "p@school-pilot.in",
                         "subject": f"About {ref}", "body": body, "related_ref": ref, "kind": "ticket",
                         "status": "logged", "error": ""})
    with db.connect() as conn:
        conn.execute("UPDATE outbox SET created_at = ? WHERE id = ?", (when, row["id"]))


def _age(table, ref, when):
    with db.connect() as conn:
        conn.execute(f"UPDATE {table} SET created_at = ?, updated_at = ? WHERE ref = ?", (when, when, ref))


def refs(table):
    return sorted(r["ref"] for r in db.list_rows(table))


# ---------- Old records ----------

def test_purge_deletes_old_closed_records_and_keeps_open_ones():
    old_closed = enquiry(status="Closed")
    old_new = enquiry(status="New", mobile="9876543211")
    old_contacted = enquiry(status="Contacted", mobile="9876543212")
    recent_closed = enquiry(status="Closed", when=RECENT, mobile="9876543213")
    old_resolved = ticket(status="Resolved")
    old_open = ticket(status="In progress", mobile="9876543214")
    email(old_resolved)
    email(old_open)
    s = sessions.get_session("old-chat-0123456789")
    sessions.save(s)
    with db.connect() as conn:
        conn.execute("UPDATE chat_sessions SET last_seen = ?", (time.time() - 400 * 86400,))

    planned = retention.purge_old(12)                       # dry run
    assert planned == {"enquiries": 1, "tickets": 1, "outbox": 1, "chat_sessions": 1}
    assert len(db.list_rows("enquiries")) == 4             # nothing deleted yet

    assert retention.purge_old(12, apply=True) == planned
    assert refs("enquiries") == sorted([old_new, old_contacted, recent_closed])
    assert old_closed not in refs("enquiries")
    assert refs("tickets") == [old_open]
    assert [r["related_ref"] for r in db.list_rows("outbox")] == [old_open]  # email kept with its open ticket
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0] == 0


def test_purge_writes_an_audit_line_without_personal_details():
    enquiry(name="Auditname Parent")
    retention.purge_old(12, apply=True)
    [entry] = retention.recent_audit()
    assert entry["action"] == "Retention purge" and "1 enquiry" in entry["detail"]
    assert "9876543210" not in entry["detail"] and "Auditname" not in entry["detail"] and "E-1" not in entry["detail"]


def test_retention_months_setting(monkeypatch):
    monkeypatch.setenv("RETENTION_MONTHS", "24")
    try:
        assert importlib.reload(config).RETENTION_MONTHS == 24
    finally:
        monkeypatch.undo()
        importlib.reload(config)
    assert config.RETENTION_MONTHS == 12


def test_purge_script_dry_run_then_apply(tmp_path):
    db_path = tmp_path / "script.db"
    db.init_db(db_path)
    enquiry()
    env = {**os.environ, "DB_PATH": str(db_path), "RETENTION_MONTHS": "12"}
    script = [sys.executable, str(ROOT / "scripts" / "purge_old_records.py")]
    dry = subprocess.run(script, capture_output=True, text=True, env=env)
    assert dry.returncode == 0 and "would delete: 1 enquiry(s)" in dry.stdout and "Dry run" in dry.stdout
    assert len(db.list_rows("enquiries")) == 1
    real = subprocess.run(script + ["--apply"], capture_output=True, text=True, env=env)
    assert real.returncode == 0 and "deleted: 1 enquiry(s)" in real.stdout
    assert db.list_rows("enquiries") == []


# ---------- One person's data ----------

def test_delete_everything_for_one_mobile(client, fake):
    mine_e = enquiry(status="New", when=RECENT)
    mine_t = ticket(status="Received", when=RECENT)
    other = enquiry(mobile="9123456780", when=RECENT, name="Other Parent")
    email(mine_t, body="Mobile: 9876543210")
    email(other, body="Mobile: 9123456780")
    s = sessions.get_session("mine-chat-0123456789")
    sessions.remember(s, Message(role="user", content="my number is 98765 43210"))
    sessions.save(s)

    login(client)
    preview = client.post("/staff/api/person/preview", json={"mobile": "+91 98765 43210"}, headers=HEADERS).json()
    assert preview["counts"] == {"enquiries": 1, "tickets": 1, "outbox": 1, "chat_sessions": 1}
    assert sorted(preview["open"]) == sorted([f"{mine_e} (New)", f"{mine_t} (Received)"])

    refused = client.post("/staff/api/person/delete", json={"mobile": "9876543210", "confirm": "yes"}, headers=HEADERS)
    assert refused.status_code == 400 and len(db.list_rows("enquiries")) == 2

    done = client.post("/staff/api/person/delete", json={"mobile": "9876543210", "confirm": "DELETE"}, headers=HEADERS)
    assert done.status_code == 200 and done.json()["deleted"]["enquiries"] == 1
    assert refs("enquiries") == [other] and db.list_rows("tickets") == []
    assert [r["related_ref"] for r in db.list_rows("outbox")] == [other]
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()[0] == 0

    [entry] = client.get("/staff/api/data").json()["audit"]
    assert entry["action"] == "Deleted on request"
    assert "9876543210" not in json.dumps(entry) and mine_e not in json.dumps(entry)


def test_person_deletion_needs_login_header_and_valid_number(client):
    body = {"mobile": "9876543210", "confirm": "DELETE"}
    assert client.post("/staff/api/person/delete", json=body, headers=HEADERS).status_code == 401
    login(client)
    assert client.post("/staff/api/person/delete", json=body).status_code == 403
    bad = client.post("/staff/api/person/preview", json={"mobile": "12345"}, headers=HEADERS)
    assert bad.status_code == 400 and "valid" in bad.json()["detail"]
