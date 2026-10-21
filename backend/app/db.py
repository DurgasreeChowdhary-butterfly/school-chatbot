"""SQLite storage for enquiries, tickets, callback requests and the notification outbox.
Uses Python's built-in sqlite3. The database file is data/chatbot.db unless DB_PATH is set."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("DB_PATH", str(ROOT / "data" / "chatbot.db")))

SCHEMA = """
CREATE TABLE IF NOT EXISTS enquiries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref TEXT UNIQUE,
    campus TEXT NOT NULL,
    parent_name TEXT NOT NULL,
    child_name TEXT NOT NULL,
    class_applying TEXT NOT NULL,
    mobile TEXT NOT NULL,
    previous_school TEXT DEFAULT '',
    reason TEXT DEFAULT '',
    visit_preference TEXT NOT NULL,
    assigned_to TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'New',
    notes TEXT DEFAULT '',
    consent_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    reminded_at TEXT,
    escalated_at TEXT
);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref TEXT UNIQUE,
    campus TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    parent_name TEXT NOT NULL,
    mobile TEXT NOT NULL,
    urgent INTEGER NOT NULL DEFAULT 0,
    first_contact TEXT NOT NULL,
    backup_contact TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Received',
    consent_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    reminded_at TEXT,
    escalated_at TEXT
);
CREATE TABLE IF NOT EXISTS callbacks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref TEXT UNIQUE,
    campus TEXT NOT NULL,
    name TEXT NOT NULL,
    mobile TEXT NOT NULL,
    reason TEXT DEFAULT '',
    assigned_to TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'New',
    consent_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campus TEXT NOT NULL,
    to_role TEXT NOT NULL,
    to_email TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    related_ref TEXT DEFAULT '',
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    error TEXT DEFAULT ''
);
"""

# Reference prefixes shown to people: E-1001, T-1001, C-1001.
PREFIX = {"enquiries": "E", "tickets": "T", "callbacks": "C"}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def init_db(path: Path | str | None = None) -> None:
    """Create the database file and tables if they don't exist yet."""
    global DB_PATH
    if path is not None:
        DB_PATH = Path(path)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def insert(table: str, row: dict) -> dict:
    """Insert a row into enquiries, tickets or callbacks, give it a reference like E-1001, return it."""
    stamp = now()
    row = {**row, "created_at": stamp, "updated_at": stamp}
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    with connect() as conn:
        cur = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(row.values()))
        ref = f"{PREFIX[table]}-{1000 + cur.lastrowid}"
        conn.execute(f"UPDATE {table} SET ref = ? WHERE id = ?", (ref, cur.lastrowid))
        return dict(conn.execute(f"SELECT * FROM {table} WHERE id = ?", (cur.lastrowid,)).fetchone())


def find_one(table: str, **where) -> dict | None:
    clause = " AND ".join(f"{k} = ?" for k in where)
    with connect() as conn:
        row = conn.execute(f"SELECT * FROM {table} WHERE {clause} ORDER BY id DESC", list(where.values())).fetchone()
        return dict(row) if row else None


def update(table: str, ref: str, **changes) -> None:
    changes["updated_at"] = now()
    sets = ", ".join(f"{k} = ?" for k in changes)
    with connect() as conn:
        conn.execute(f"UPDATE {table} SET {sets} WHERE ref = ?", [*changes.values(), ref])


def list_rows(table: str) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY id DESC")]


def add_outbox(row: dict) -> dict:
    row = {**row, "created_at": now()}
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    with connect() as conn:
        cur = conn.execute(f"INSERT INTO outbox ({cols}) VALUES ({marks})", list(row.values()))
        return dict(conn.execute("SELECT * FROM outbox WHERE id = ?", (cur.lastrowid,)).fetchone())
