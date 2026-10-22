"""Staff page at /staff: login with ADMIN_PASSWORD, see enquiries, tickets, callbacks and the outbox,
change statuses, resend emails, export CSV, and run the reminder job by hand."""
import asyncio
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

from . import config, db, jobs, notify, retention, unanswered

log = logging.getLogger("chatbot.staff")
router = APIRouter()
PAGES = Path(__file__).resolve().parent / "staff_pages"

COOKIE = "staff_session"
SESSION_SECONDS = 8 * 60 * 60          # staff stay logged in for 8 hours
MAX_FAILED_LOGINS = 5                   # per IP address ...
FAILED_LOGIN_WINDOW = 15 * 60           # ... in 15 minutes
# Failures from all addresses together in 15 minutes above which we treat it as a possible attack. Nobody is locked
# out (that would let an attacker lock out the staff): each further wrong attempt just waits longer before its answer.
ATTACK_THRESHOLD = 50
ATTACK_DELAY_STEP = 0.5                 # seconds added per wrong attempt over the threshold ...
ATTACK_DELAY_MAX = 10.0                 # ... up to this
MIN_PASSWORD_LENGTH = 12

STATUSES = {
    "enquiries": ["New", "Contacted", "Visit booked", "Closed"],
    "tickets": ["Received", "In progress", "Resolved"],
    "callbacks": ["New", "Called back"],
}
EXPORTS = {"enquiries", "tickets", "callbacks", "outbox"}

_tokens: dict[str, float] = {}          # login token -> expiry time
_failed: dict[str, deque] = defaultdict(deque)  # IP -> times of failed logins
_attack = {"since": 0.0, "logged_at": 0}  # when the current possible attack started, failures count when last logged
_lock = threading.Lock()


def reset_state() -> None:
    """Forget all logins and failed attempts (used by tests)."""
    with _lock:
        _tokens.clear()
        _failed.clear()
        _attack.update(since=0.0, logged_at=0)


def _admin_password() -> str:
    """The staff password, or "" (login off) if it is missing or too short to resist guessing."""
    password = os.getenv("ADMIN_PASSWORD", "").strip()
    return password if len(password) >= MIN_PASSWORD_LENGTH else ""


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


def _forget_old_failures() -> None:
    cutoff = time.time() - FAILED_LOGIN_WINDOW
    for ip in list(_failed):
        attempts = _failed[ip]
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        if not attempts:
            del _failed[ip]


def _too_many_failures(ip: str) -> bool:
    """Only this address is blocked (5 wrong passwords in 15 minutes)."""
    with _lock:
        _forget_old_failures()
        return len(_failed.get(ip, ())) >= MAX_FAILED_LOGINS


def login_alert() -> dict | None:
    """A possible attack: many wrong passwords from all addresses together in the last 15 minutes. None if calm."""
    with _lock:
        _forget_old_failures()
        total = sum(len(a) for a in _failed.values())
        if total < ATTACK_THRESHOLD:
            _attack.update(since=0.0, logged_at=0)
            return None
        return {"failures": total, "addresses": len(_failed), "since": _attack["since"] or time.time(),
                "minutes": FAILED_LOGIN_WINDOW // 60}


def _record_failure(ip: str) -> float:
    """Remember a wrong password. Returns how long to wait before answering (0 unless under a possible attack)."""
    with _lock:
        _failed[ip].append(time.time())
    alert = login_alert()
    if not alert:
        return 0.0
    with _lock:
        if not _attack["since"]:
            _attack["since"] = time.time()
        # Log when it starts, then every 50 more failures (not every attempt, so the log stays readable).
        if alert["failures"] - _attack["logged_at"] >= 50 or not _attack["logged_at"]:
            _attack["logged_at"] = alert["failures"]
            log.warning("Possible attack on the staff login: %s wrong passwords from %s addresses in %s minutes; "
                        "wrong attempts are being slowed down", alert["failures"], alert["addresses"], alert["minutes"])
    excess = alert["failures"] - ATTACK_THRESHOLD + 1
    return min(ATTACK_DELAY_MAX, ATTACK_DELAY_STEP * excess)


def _login_page(message: str = "", status_code: int = 200) -> HTMLResponse:
    html = (PAGES / "login.html").read_text(encoding="utf-8")
    html = html.replace("{{message}}", message).replace("{{demo_hidden}}", "" if config.DEMO_MODE else "hidden")
    return HTMLResponse(html, status_code=status_code)


# ---------- Pages and login ----------

@router.get("/staff", include_in_schema=False)
def staff_page(request: Request):
    if not _logged_in(request):
        if not _admin_password():
            return _login_page("Staff login is switched off: set ADMIN_PASSWORD in .env (at least 12 characters) and restart the server.", 503)
        return _login_page()
    return FileResponse(PAGES / "staff.html")


@router.post("/staff/login", include_in_schema=False)
async def login(request: Request, password: str = Form("")):
    ip = _client_ip(request)
    expected = _admin_password()
    if not expected:
        return _login_page("Staff login is switched off: set ADMIN_PASSWORD in .env (at least 12 characters) and restart the server.", 503)
    if _too_many_failures(ip):
        log.warning("Staff login blocked for %s: too many failed attempts", ip)
        return _login_page("Too many wrong attempts. Please wait 15 minutes and try again.", 429)
    if not hmac.compare_digest(password.encode("utf-8"), expected.encode("utf-8")):
        delay = _record_failure(ip)
        log.warning("Staff login failed from %s", ip)
        if delay:
            await asyncio.sleep(delay)  # waits without holding a server thread
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
        "email_on": notify.smtp_configured(),
        "test_mode": notify.test_mode(),
        "login_alert": login_alert(),
        "audit": retention.recent_audit(),
        "unanswered": unanswered.open_questions(),
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


class Resend(BaseModel):
    id: int


@router.post("/staff/api/resend")
def resend_email(req: Resend, request: Request):
    _require_login(request)
    _require_same_site_request(request)
    if not notify.smtp_configured():
        raise HTTPException(status_code=400, detail="Email is not set up (SMTP_HOST is empty in .env).")
    row = notify.resend(req.id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found.")
    log.info("Staff resent email %s: %s", req.id, row["status"])
    return {"ok": True, "status": row["status"], "error": row["error"]}


@router.post("/staff/api/unanswered/{question_id}/done")
def unanswered_done(question_id: int, request: Request):
    """Staff added the missing information to the knowledge files."""
    _require_login(request)
    _require_same_site_request(request)
    if not unanswered.mark_content_added(question_id):
        raise HTTPException(status_code=404, detail="Not found.")
    return {"ok": True}


class Person(BaseModel):
    mobile: str
    confirm: str = ""


@router.post("/staff/api/person/preview")
def person_preview(req: Person, request: Request):
    """Step 1 of a deletion request: what is stored for this mobile number (counts only)."""
    _require_login(request)
    _require_same_site_request(request)
    try:
        return retention.preview_person(req.mobile)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/staff/api/person/delete")
def person_delete(req: Person, request: Request):
    """Step 2: delete everything for this mobile number. The staff member must type DELETE to confirm."""
    _require_login(request)
    _require_same_site_request(request)
    if req.confirm != "DELETE":
        raise HTTPException(status_code=400, detail="Type DELETE to confirm.")
    try:
        return {"deleted": retention.delete_person(req.mobile)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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
