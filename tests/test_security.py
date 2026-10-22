"""Security review fixes and checks (docs/security-review.md): headers, cookies, brute force, SQL injection,
CSRF, data leaks in logs, and the CORS and API-docs settings."""
import importlib
import io
import logging
import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import config, db, main, security, staff
from tests.conftest import tool_turn
from tests.test_staff import HEADERS, add_enquiry, login

ROOT = Path(__file__).resolve().parents[1]


# ---------- Security headers ----------

def test_every_response_has_basic_security_headers(client):
    for path in ("/health", "/config", "/widget/chat.js", "/demo", "/staff"):
        h = client.get(path).headers
        assert h["x-content-type-options"] == "nosniff", path
        assert h["x-frame-options"] == "DENY", path
        assert h["referrer-policy"] == "strict-origin-when-cross-origin", path
        assert "strict-transport-security" not in h  # plain http here


def test_https_gets_hsts(fake):
    with TestClient(main.app, base_url="https://testserver") as c:
        assert c.get("/health").headers["strict-transport-security"] == "max-age=31536000"


def test_staff_pages_have_strict_csp_and_no_caching(client):
    login(client)
    for path in ("/staff", "/staff/api/data", "/staff/export/enquiries.csv"):
        h = client.get(path).headers
        assert "script-src 'self' 'sha256-" in h["content-security-policy"], path
        assert "frame-ancestors 'none'" in h["content-security-policy"]
        assert h["cache-control"] == "no-store", path
    assert client.post("/chat", json={"session_id": "s1-0123456789abcdef", "message": "hi"}).headers["cache-control"] == "no-store"


def test_csp_hash_matches_the_staff_page_script():
    import base64
    import hashlib
    import re
    page = (security.PAGES / "staff.html").read_text(encoding="utf-8")
    [script] = re.findall(r"<script>(.*?)</script>", page, re.S)
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    assert f"'sha256-{digest}'" in security.STAFF_CSP


# ---------- Staff cookie ----------

def test_login_cookie_flags(client):
    cookie = login(client).headers["set-cookie"].lower()
    for flag in ("httponly", "samesite=strict", "path=/staff", "max-age=28800"):
        assert flag in cookie
    assert "secure" not in cookie  # plain http in tests


def test_login_cookie_is_secure_over_https(fake):
    with TestClient(main.app, base_url="https://testserver") as c:
        assert "secure" in login(c).headers["set-cookie"].lower()


# ---------- Login brute force ----------

def test_short_password_switches_login_off(client, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "short-pass1")  # 11 characters
    r = login(client, "short-pass1")
    assert r.status_code == 503 and "at least 12 characters" in r.text


def test_failures_from_many_addresses_block_all_logins(client):
    with staff._lock:
        for n in range(staff.MAX_FAILED_LOGINS_ALL):
            staff._failed[f"10.0.{n // 250}.{n % 250}"].append(time.time())  # one failure each from 50 addresses
    r = login(client)  # right password, new address
    assert r.status_code == 429 and "Too many wrong attempts" in r.text


def test_old_failures_expire(client):
    with staff._lock:
        for n in range(staff.MAX_FAILED_LOGINS_ALL):
            staff._failed[f"10.1.0.{n}"].append(time.time() - staff.FAILED_LOGIN_WINDOW - 1)
    assert login(client).status_code == 303


# ---------- SQL injection ----------

def test_sql_injection_in_staff_api_is_refused(client):
    add_enquiry()
    login(client)
    bad = client.post("/staff/api/status", headers=HEADERS,
                      json={"kind": "enquiries; DROP TABLE enquiries;--", "ref": "E-1001", "status": "Closed"})
    assert bad.status_code == 400
    bad_ref = client.post("/staff/api/status", headers=HEADERS,
                          json={"kind": "enquiries", "ref": "E-1001' OR '1'='1", "status": "Closed"})
    assert bad_ref.status_code == 404
    assert client.get("/staff/export/enquiries%3B%20DROP%20TABLE%20x.csv").status_code == 404
    assert db.find_one("enquiries", ref="E-1001")["status"] == "New"


def test_sql_injection_through_the_chat_tools(client, fake):
    payload = "x'); DROP TABLE tickets; --"
    [lookup] = tool_turn(client, fake, "status", ("get_ticket_status", {"ticket_ref": "T-1' OR '1'='1",
                                                                        "mobile": "9876543210"}), session_id="sql1")
    assert "error" in lookup
    [bad_name] = tool_turn(client, fake, "log", ("create_ticket", {"category": "Transport", "description": "late bus",
                                                                   "parent_name": payload, "mobile": "9876543210"}),
                           session_id="sql2")
    assert "parent_name" in bad_name["problems"]
    [saved] = tool_turn(client, fake, "log", ("create_ticket", {"category": "Transport", "description": payload,
                                                                "parent_name": "Sample Parent", "mobile": "9876543210"}),
                        session_id="sql3")
    assert saved["status"] == "created"
    assert db.list_rows("tickets")[0]["description"] == payload  # stored as plain text; the table is still there


# ---------- CSRF ----------

def test_staff_actions_need_the_staff_page_header(client):
    add_enquiry()
    login(client)
    for path, body in (("/staff/api/status", {"kind": "enquiries", "ref": "E-1001", "status": "Closed"}),
                       ("/staff/api/run-reminders", {}), ("/staff/api/resend", {"id": 1})):
        assert client.post(path, json=body).status_code == 403, path
    # A cross-site form can only send form data, never JSON with our header.
    form = client.post("/staff/api/status", data={"kind": "enquiries", "ref": "E-1001", "status": "Closed"})
    assert form.status_code in (403, 422)
    assert db.find_one("enquiries", ref="E-1001")["status"] == "New"


# ---------- Leaks ----------

def test_logs_never_contain_names_or_numbers(client, fake):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logging.getLogger("chatbot").addHandler(handler)
    try:
        details = {"parent_name": "Leaky Parentname", "child_name": "Leaky Childname", "class_applying": "Grade 3",
                   "mobile": "9876543210", "visit_preference": "Saturday"}
        tool_turn(client, fake, "details", ("submit_enquiry", details), session_id="leak")
        tool_turn(client, fake, "yes", ("confirm_enquiry", {}), session_id="leak")
        tool_turn(client, fake, "log", ("create_ticket", {"category": "Transport", "description": "Leaky description",
                                                          "parent_name": "Leaky Parentname", "mobile": "9876543210"}),
                  session_id="leak2")
    finally:
        logging.getLogger("chatbot").removeHandler(handler)
    text = stream.getvalue()
    assert "E-1001" in text and "T-1001" in text
    for secret in ("Leaky", "9876543210", "Leaky description"):
        assert secret not in text


def test_staff_data_and_exports_need_login(client):
    add_enquiry()
    for path in ("/staff/api/data", "/staff/export/enquiries.csv", "/staff/export/outbox.csv"):
        r = client.get(path)
        assert r.status_code == 401 and "Sample Parent" not in r.text


# ---------- Settings: CORS and API docs ----------

def test_cors_refuses_wildcards_and_paths(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "*, https://www.school.example, https://evil.example/path, http://plain.example,"
                                          " http://localhost:5500")
    try:
        reloaded = importlib.reload(config)
        assert reloaded.ALLOWED_ORIGINS == ["https://www.school.example", "http://plain.example", "http://localhost:5500"]
        assert any("'*' ignored" in w for w in reloaded.WARNINGS)
        assert any("evil.example/path" in w for w in reloaded.WARNINGS)
        assert any("plain.example uses http" in w for w in reloaded.WARNINGS)
        assert not any("localhost" in w for w in reloaded.WARNINGS)
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_api_docs_are_off_when_live(tmp_path):
    port = _free_port()
    env = {**os.environ, "LLM_PROVIDER": "fake", "DEMO_MODE": "false", "DB_PATH": str(tmp_path / "live.db")}
    env.pop("API_DOCS", None)
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app.main:app", "--port", str(port)], cwd=ROOT,
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert httpx.get(f"http://127.0.0.1:{port}{path}").status_code == 404, path
    finally:
        proc.kill()


def test_api_docs_are_on_in_demo_mode(client):
    assert client.get("/openapi.json").status_code == 200


def test_database_file_has_no_secrets():
    """Secrets live only in .env: the database never stores the staff password or API keys."""
    db.init_db()
    with sqlite3.connect(db.DB_PATH) as conn:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for table in tables:
            columns = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
            assert not any(c in ("password", "api_key", "token") for c in columns), table
