"""Put a backup (made by scripts/backup_db.py) back as the chatbot's database.

Usage:
    python scripts/restore_db.py data/backups/chatbot-20261101-023000.db            # shows what it will do, asks
    python scripts/restore_db.py data/backups/chatbot-20261101-023000.db --yes      # no question (for scripts)
    python scripts/restore_db.py BACKUP --db D:/somewhere/chatbot.db                 # restore to another place

Stop the server first (it must not write while the database is replaced), then start it again afterwards.
What it does:
1. Checks the backup is a complete, undamaged chatbot database and shows how many records it holds.
2. Keeps the current database as <name>.before-restore-<date-time>.db (so the restore can be undone).
3. Copies the backup into place with SQLite's own copy (safe and complete)."""
import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = ["enquiries", "tickets", "callbacks", "outbox"]


def check_backup(path: Path) -> dict[str, int]:
    """Counts per table. Raises ValueError (plain words) if the file is not a usable chatbot backup."""
    if not path.is_file():
        raise ValueError(f"There is no file at {path}.")
    try:
        with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as conn:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("The backup file is damaged. Try an older backup.")
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            missing = [t for t in TABLES if t not in tables]
            if missing:
                raise ValueError(f"This is not a chatbot backup (no {', '.join(missing)} table).")
            return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    except sqlite3.DatabaseError as e:
        raise ValueError(f"This file is not a database the chatbot can use ({e}).") from None


def restore(backup: Path, target: Path) -> Path | None:
    """Copy `backup` over `target`. Returns where the old database was kept (None if there was none)."""
    kept = None
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        kept = target.with_name(f"{target.stem}.before-restore-{datetime.now():%Y%m%d-%H%M%S}.db")
        shutil.copy2(target, kept)
    with sqlite3.connect(backup) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    return kept


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup", help="the backup file to restore")
    parser.add_argument("--db", default=os.getenv("DB_PATH", str(ROOT / "data" / "chatbot.db")),
                        help="the database to replace (default: DB_PATH, or data/chatbot.db)")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    args = parser.parse_args()
    backup, target = Path(args.backup), Path(args.db)
    try:
        counts = check_backup(backup)
    except ValueError as e:
        print(f"NOT RESTORED: {e}")
        return 1
    print(f"Backup {backup.name} is complete: " + ", ".join(f"{n} {t}" for t, n in counts.items()) + ".")
    print(f"It will replace: {target}" + ("" if target.exists() else " (no database there yet)"))
    print("The server must be stopped now.")
    if not args.yes and input("Type YES to restore: ").strip() != "YES":
        print("Nothing was changed.")
        return 1
    kept = restore(backup, target)
    if kept:
        print(f"The old database was kept as {kept.name} (to undo, restore that file the same way).")
    print("Restored. Start the server again, then check /health and the staff page.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
