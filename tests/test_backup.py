"""scripts/backup_db.py makes a readable copy of the database and keeps only the newest copies."""
import sqlite3
import subprocess
import sys
from pathlib import Path

from backend.app import db

ROOT = Path(__file__).resolve().parents[1]


def test_backup_copies_the_database_and_prunes_old_copies(tmp_path):
    db.insert("callbacks", {"campus": "pilot-campus", "name": "Sample Parent", "mobile": "9876543210",
                            "assigned_to": "Front office"})
    backups = tmp_path / "backups"
    backups.mkdir()
    for n in range(3):
        (backups / f"chatbot-2020010{n}-000000.db").write_bytes(b"old")
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "backup_db.py"), "--db", str(db.DB_PATH),
                          "--to", str(backups), "--keep", "2"], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    copies = sorted(backups.glob("chatbot-*.db"))
    assert len(copies) == 2 and copies[0].name == "chatbot-20200102-000000.db"
    with sqlite3.connect(copies[-1]) as conn:
        assert conn.execute("SELECT name FROM callbacks").fetchone()[0] == "Sample Parent"
