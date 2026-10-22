"""Backup and restore, end to end: fill a database, back it up with scripts/backup_db.py, restore it into a fresh
folder with scripts/restore_db.py, start a server on the restored copy, and check the staff page shows the same
enquiries, tickets and callbacks as the original."""
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from backend.app import db
from scripts.restore_db import check_backup, restore
from tests.test_widget_browser import free_port

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "restore-test-password"


def fill(path: Path) -> None:
    db.init_db(path)
    for n in range(3):
        db.insert("enquiries", {"campus": "pilot-campus", "parent_name": f"Sample Parent {'ABC'[n]}",
                                "child_name": "Sample Kid", "class_applying": f"Grade {n + 1}",
                                "mobile": f"98765432{10 + n}", "visit_preference": "Saturday",
                                "assigned_to": "Admission counsellor"})
    t = db.insert("tickets", {"campus": "pilot-campus", "category": "Transport", "description": "Bus late",
                              "parent_name": "Sample Parent", "mobile": "9876543210", "urgent": 0,
                              "first_contact": "Transport coordinator", "backup_contact": "Principal"})
    db.update("tickets", t["ref"], status="In progress")
    db.insert("callbacks", {"campus": "pilot-campus", "name": "Sample Parent", "mobile": "9876543210",
                            "assigned_to": "Front office"})


def staff_data(db_path: Path) -> dict:
    """Start a server on this database, log in to the staff page and return what it shows."""
    port = free_port()
    env = {**os.environ, "LLM_PROVIDER": "fake", "DB_PATH": str(db_path), "ADMIN_PASSWORD": PASSWORD}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app.main:app", "--port", str(port)], cwd=ROOT,
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                if httpx.get(url + "/health", timeout=1).json()["database"] == "ok":
                    break
            except (httpx.HTTPError, ValueError, KeyError):
                time.sleep(0.2)
        with httpx.Client(base_url=url) as c:
            assert c.post("/staff/login", data={"password": PASSWORD}).status_code in (200, 303)
            return c.get("/staff/api/data").json()
    finally:
        proc.kill()


def test_backup_then_restore_into_a_fresh_folder_shows_the_same_data(tmp_path):
    original = tmp_path / "live" / "chatbot.db"
    fill(original)
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "backup_db.py"), "--db", str(original)],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    [backup] = (original.parent / "backups").glob("chatbot-*.db")

    fresh = tmp_path / "new-server" / "data" / "chatbot.db"     # a fresh folder, as on a new server
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "restore_db.py"), str(backup), "--db", str(fresh),
                          "--yes"], capture_output=True, text=True)
    assert run.returncode == 0 and "3 enquiries, 1 tickets, 1 callbacks" in run.stdout, run.stdout

    before, after = staff_data(original), staff_data(fresh)
    for table in ("enquiries", "tickets", "callbacks"):
        assert after[table] == before[table], table
    assert len(after["enquiries"]) == 3 and after["tickets"][0]["status"] == "In progress"


def test_restore_keeps_the_old_database_and_refuses_bad_files(tmp_path):
    current, backup = tmp_path / "chatbot.db", tmp_path / "backup.db"
    fill(backup)
    db.init_db(current)
    kept = restore(backup, current)
    assert kept.exists() and "before-restore" in kept.name
    with sqlite3.connect(current) as conn:
        assert conn.execute("SELECT COUNT(*) FROM enquiries").fetchone()[0] == 3

    (tmp_path / "not-a-db.db").write_text("hello")
    with pytest.raises(ValueError, match="not a database"):
        check_backup(tmp_path / "not-a-db.db")
    with sqlite3.connect(tmp_path / "other.db") as conn:
        conn.execute("CREATE TABLE notes (x)")
    with pytest.raises(ValueError, match="not a chatbot backup"):
        check_backup(tmp_path / "other.db")
    with pytest.raises(ValueError, match="no file"):
        check_backup(tmp_path / "missing.db")


def test_restore_asks_before_replacing(tmp_path):
    backup = tmp_path / "backup.db"
    fill(backup)
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "restore_db.py"), str(backup),
                          "--db", str(tmp_path / "x.db")], input="no\n", capture_output=True, text=True)
    assert run.returncode == 1 and "Nothing was changed" in run.stdout and not (tmp_path / "x.db").exists()
