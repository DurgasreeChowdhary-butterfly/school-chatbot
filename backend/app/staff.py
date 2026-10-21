"""Staff page at /staff: login with ADMIN_PASSWORD, see enquiries, tickets, callbacks and the outbox,
change statuses, export CSV, and run the reminder job by hand."""
import csv
import hmac
import io
import logging
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel

from . import config, db, jobs

log = logging.getLogger("chatbot.staff")
router = APIRouter()
PAGES = Path(__file__).resolve().parent / "staff_pages"

COOKIE = "staff_session"
SESSION_SECONDS = 8 * 60 * 60          # staff stay logged in for 8 hours
MAX_FAILED_LOGINS = 5                   # per IP address ...
FAILED_LOGIN_WINDOW = 15 * 60           # ... in 15 minutes

STATUSES = {
    "enquiries": ["New", "Contacted", "Visit booked", "Closed"],
    "tickets": ["Received", "In progress", "Resolved"],
    "callbacks": ["New", "Called back"],
}
EXPORTS = {"enquiries", "tickets", "callbacks", "outbox"}

_tokens: dict[str, float] = {}          # login token -> expiry time
_failed: dict[str, deque] = defaultdict(deque)  # IP -> times of failed logins
_lock = threading.Lock()


def reset_state() -> None:
    """Forget all logins and failed attempts (used by tests)."""
    with _lock:
        _tokens.clear()
        _failed.clear()


def _admin_password() -> str:
    return os.getenv("ADMIN_PASSWORD", "").strip()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _logged_in(request: Request) -> bool:
    token = request.cookies.get(COOKIE, "")
    with _lock:
        expiry = _tokens.get(token)
        if expiry and expiry > time.time():
            return True
        _tokens.pop(token, None)
        return False


def _require_login(request: Request) -> None:
    if not _logged_in(request):
        raise HTTPException(status_code=401, detail="Please log in.")


def _require_same_site_request(request: Request) -> None:
    # Our page sends this header; a form on another website cannot.
    if request.headers.get("X-Requested-With") != "staff-page":
        raise HTTPException(status_code=403, detail="Missing request header.")


def _too_many_failures(ip: str) -> bool:
    cutoff = time.time() - FAILED_LOGIN_WINDOW
    with _lock:
        attempts = _failed[ip]
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        return len(attempts) >= MAX_FAILED_LOGINS


def _login_page(message: str = "", status_code: int = 200) -> HTMLResponse:
    html = (PAGES / "login.html").read_text(encoding="utf-8")
    html = html.replace("{{message}}", message).replace("{{demo_hidden}}", "" if config.DEMO_MODE else "hidden")
    return HTMLResponse(html, status_code=status_code)


# ---------- Pages and login ----------

@router.get("/staff", include_in_schema=False)
def staff_page(request: Request):
    if not _logged_in(request):
        if not _admin_password():
            return _login_page("Staff login is switched off: set ADMIN_PASSWORD in .env and restart the server.", 503)
        return _login_page()
    return FileResponse(PAGES / "staff.html")


@router.post("/staff/login", include_in_schema=False)
def login(request: Request, password: str = Form("")):
    ip = _client_ip(request)
    expected = _admin_password()
    if not expected:
        return _login_page("Staff login is switched off: set ADMIN_PASSWORD in .env and restart the server.", 503)
    if _too_many_failures(ip):
        log.warning("Staff login blocked for %s: too many failed attempts", ip)
        return _login_page("Too many wrong attempts. Please wait 15 minutes and try again.", 429)
    if not hmac.compare_digest(password.encode("utf-8"), expected.encode("utf-8")):
        with _lock:
            _failed[ip].append(time.time())
        log.warning("Staff login failed from %s", ip)
        return _login_page("Wrong password.", 401)

    token = secrets.token_urlsafe(32)
    with _lock:
        _tokens[token] = time.time() + SESSION_SECONDS
        _failed.pop(ip, None)
    log.info("Staff login from %s", ip)
    response = RedirectResponse("/staff", status_code=303)
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, samesite="strict",
                        secure=request.url.scheme == "https", path="/staff")
    return response


@router.post("/staff/logout", include_in_schema=False)
def logout(request: Request):
    with _lock:
        _tokens.pop(request.cookies.get(COOKIE, ""), None)
    response = RedirectResponse("/staff", status_code=303)
    response.delete_cookie(COOKIE, path="/staff")
    return response


# ---------- Data for the staff page ----------

@router.get("/staff/api/data")
def staff_data(request: Request):
    _require_login(request)
    return {
        "demo": config.DEMO_MODE,
        "statuses": STATUSES,
        "enquiries": db.list_rows("enquiries"),
        "tickets": db.list_rows("tickets"),
        "callbacks": db.list_rows("callbacks"),
        "outbox": db.list_rows("outbox")[:300],
    }


class StatusChange(BaseModel):
    kind: str
    ref: str
    status: str


@router.post("/staff/api/status")
def change_status(change: StatusChange, request: Request):
    _require_login(request)
    _require_same_site_request(request)
    if change.kind not in STATUSES or change.status not in STATUSES[change.kind]:
        raise HTTPException(status_code=400, detail="Unknown status.")
    if not db.find_one(change.kind, ref=change.ref):
        raise HTTPException(status_code=404, detail="Not found.")
    db.update(change.kind, change.ref, status=change.status)
    log.info("Staff set %s %s to %s", change.kind, change.ref, change.status)
    return {"ok": True}


@router.post("/staff/api/run-reminders")
def run_reminders_now(request: Request):
    _require_login(request)
    _require_same_site_request(request)
    return {"notifications": jobs.run_reminders()}


@router.get("/staff/export/{kind}.csv")
def export_csv(kind: str, request: Request):
    _require_login(request)
    if kind not in EXPORTS:
        raise HTTPException(status_code=404, detail="Unknown export.")
    rows = db.list_rows(kind)
    out = io.StringIO()
    if rows:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({k: _safe_cell(v) for k, v in r.items()} for r in rows)
    return Response(
        out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{kind}.csv"'},
    )


def _safe_cell(value):
    """Stop spreadsheet programs from running text that looks like a formula (=, +, -, @)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value
