"""Delete records older than RETENTION_MONTHS (default 12, set in .env), as the privacy notice promises.

Usage:
    python scripts/purge_old_records.py              # dry run: only shows what would be deleted
    python scripts/purge_old_records.py --apply      # really deletes
    python scripts/purge_old_records.py --months 6   # a different limit for this run

Deletes chats, enquiries, tickets, callbacks and notification emails whose last change is older than the limit.
Never deletes enquiries still being followed up (New, Contacted, Visit booked), open tickets (Received, In progress)
or callbacks not yet made. Each real run adds a line to the audit log (counts only, no personal details).
Make a backup first (scripts/backup_db.py); docs/deploy.md shows how to run both every night."""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from backend.app import config, db, retention  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=config.RETENTION_MONTHS)
    parser.add_argument("--apply", action="store_true", help="really delete (default: dry run)")
    args = parser.parse_args()
    if args.months < 1:
        print("--months must be at least 1.")
        return 1
    db.init_db()
    counts = retention.purge_old(args.months, apply=args.apply)
    limit = retention.cutoff(args.months).strftime("%d %b %Y")
    print(f"Database: {os.getenv('DB_PATH') or db.DB_PATH}")
    print(f"Limit: {args.months} months (last change before {limit}). Open and followed-up records are kept.")
    if not counts:
        print("Nothing to delete.")
    for table, n in counts.items():
        print(f"  {'deleted' if args.apply else 'would delete'}: {n} {retention.NAMES[table]}(s)")
    if counts and not args.apply:
        print("Dry run: nothing was deleted. Run again with --apply to delete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
