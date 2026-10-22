"""Deleting personal data: old records after RETENTION_MONTHS (the privacy notice promises this), and everything
for one mobile number when a parent asks. Both write an audit line that holds no personal details.

Kept whatever their age: enquiries still being followed up, open tickets and callbacks not yet made.
Age is counted from a record's last change (updated_at), so anything still being worked on stays."""
import json
import logging
import re
from datetime import datetime, timedelta

from . import db
from .validation import normalize_mobile

log = logging.getLogger("chatbot.retention")

KEEP_STATUSES = {  # still being followed up: never deleted for age
    "enquiries": ("New", "Contacted", "Visit booked"),
    "tickets": ("Received", "In progress"),
    "callbacks": ("New",),
}
NAMES = {"enquiries": "enquiry", "tickets": "ticket", "callbacks": "callback", "outbox": "email",
         "chat_sessions": "chat", "unanswered": "unanswered question"}


def cutoff(months: int, now: datetime | None = None) -> datetime:
    return (now or datetime.now()) - timedelta(days=round(months * 30.4375))


def _plural(counts: dict) -> str:
    return ", ".join(f"{n} {NAMES[t]}{'' if n == 1 else 's'}" for t, n in counts.items()) or "nothing"


def audit(action: str, detail: str) -> None:
    """Who did what, without personal details (no numbers, names or references)."""
    with db.connect() as conn:
        conn.execute("INSERT INTO audit_log (at, action, detail) VALUES (?, ?, ?)", (db.now(), action, detail))


# ---------- Old records ----------

def purge_old(months: int, apply: bool = False, now: datetime | None = None) -> dict[str, int]:
    """Records older than `months` (dry run unless apply=True). Returns how many of each would be/were deleted."""
    limit = cutoff(months, now)
    stamp = limit.isoformat(timespec="seconds")
    plan: dict[str, list] = {}
    with db.connect() as conn:
        for table, keep in KEEP_STATUSES.items():
            marks = ", ".join("?" for _ in keep)
            plan[table] = [r["id"] for r in conn.execute(
                f"SELECT id FROM {table} WHERE updated_at < ? AND status NOT IN ({marks})", (stamp, *keep))]
        kept_refs = set()
        for table in KEEP_STATUSES:
            ids = set(plan[table])
            kept_refs |= {r["ref"] for r in conn.execute(f"SELECT id, ref FROM {table}") if r["id"] not in ids}
        plan["outbox"] = [r["id"] for r in conn.execute("SELECT id, related_ref FROM outbox WHERE created_at < ?", (stamp,))
                          if r["related_ref"] not in kept_refs]
        plan["chat_sessions"] = [r["id"] for r in conn.execute(
            "SELECT id FROM chat_sessions WHERE last_seen < ?", (limit.timestamp(),))]
        counts = {t: len(ids) for t, ids in plan.items() if ids}
        if apply:
            for table, ids in plan.items():
                for i in range(0, len(ids), 500):
                    chunk = ids[i:i + 500]
                    conn.execute(f"DELETE FROM {table} WHERE id IN ({', '.join('?' for _ in chunk)})", chunk)
    if apply:
        audit("Retention purge", f"Older than {months} months: deleted {_plural(counts)}")
        log.info("Retention purge (%s months): deleted %s", months, _plural(counts))
    return counts


# ---------- One person's data, on request ----------

def find_person(mobile: str) -> dict[str, list]:
    """Everything stored for this mobile number: {table: [ids]}."""
    number = normalize_mobile(mobile)
    if not number:
        raise ValueError("Not a valid 10-digit mobile number.")
    found: dict[str, list] = {}
    refs = set()
    with db.connect() as conn:
        for table in ("enquiries", "tickets", "callbacks"):
            rows = list(conn.execute(f"SELECT id, ref FROM {table} WHERE mobile = ?", (number,)))
            found[table] = [r["id"] for r in rows]
            refs |= {r["ref"] for r in rows}
        found["outbox"] = [r["id"] for r in conn.execute("SELECT id, related_ref, body FROM outbox")
                           if r["related_ref"] in refs or number in re.sub(r"\D", "", r["body"] or "")]
        found["chat_sessions"] = [r["id"] for r in conn.execute("SELECT id, history FROM chat_sessions")
                                  if number in re.sub(r"\D", "", _text(r["history"]))]
    return {t: ids for t, ids in found.items() if ids}


def _text(history: str) -> str:
    try:
        return " ".join(m.get("content", "") for m in json.loads(history))
    except (ValueError, TypeError):
        return history or ""


def preview_person(mobile: str) -> dict:
    found = find_person(mobile)
    open_items = []
    with db.connect() as conn:
        for table, keep in KEEP_STATUSES.items():
            for i in found.get(table, []):
                row = conn.execute(f"SELECT ref, status FROM {table} WHERE id = ?", (i,)).fetchone()
                if row["status"] in keep:
                    open_items.append(f"{row['ref']} ({row['status']})")
    return {"counts": {t: len(ids) for t, ids in found.items()}, "open": open_items}


def delete_person(mobile: str) -> dict[str, int]:
    found = find_person(mobile)
    with db.connect() as conn:
        for table, ids in found.items():
            conn.execute(f"DELETE FROM {table} WHERE id IN ({', '.join('?' for _ in ids)})", ids)
    counts = {t: len(ids) for t, ids in found.items()}
    audit("Deleted on request", f"One person's data: {_plural(counts)}")
    log.info("Deleted one person's data on request: %s", _plural(counts))
    return counts


def recent_audit(limit: int = 50) -> list[dict]:
    with db.connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))]
