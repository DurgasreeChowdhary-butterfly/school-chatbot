"""Make a safe copy of the SQLite database (works while the server is running).

Usage:
    python scripts/backup_db.py                      # copy to data/backups/, keep the newest 30 copies
    python scripts/backup_db.py --keep 60 --to D:/backups

The copy holds parents' names and mobile numbers: keep it somewhere only authorised staff can open,
and delete old copies in line with the privacy notice (records are kept for 12 months)."""
import argparse
import os
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.getenv("DB_PATH", str(ROOT / "data" / "chatbot.db")))
    parser.add_argument("--to", default=None, help="backup folder (default: a 'backups' folder next to the database)")
    parser.add_argument("--keep", type=int, default=30, help="how many copies to keep")
    args = parser.parse_args()

    source = Path(args.db)
    if not source.exists():
        raise SystemExit(f"No database at {source}")
    folder = Path(args.to) if args.to else source.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"chatbot-{datetime.now():%Y%m%d-%H%M%S}.db"

    # SQLite's own backup copies a consistent snapshot even while the server is writing.
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    with sqlite3.connect(target) as check:
        ok = check.execute("PRAGMA integrity_check").fetchone()[0]
    if ok != "ok":
        raise SystemExit(f"Backup {target} failed its integrity check: {ok}")
    print(f"Backup saved: {target}")

    copies = sorted(folder.glob("chatbot-*.db"))
    for old in copies[:-args.keep] if args.keep > 0 else []:
        old.unlink()
        print(f"Deleted old backup: {old.name}")


if __name__ == "__main__":
    main()
