"""Notifications to staff. Every notification is written to the outbox table first, then emailed.

Outbox status:
- logged:  email is not set up (SMTP_HOST empty), so it is only in the outbox and the log
- pending: waiting to be sent (urgent ones are sent first, then the oldest)
- sent:    the mail server accepted it (sent_to says which address got it)
- failed:  the last try failed; it is retried later, up to MAX_ATTEMPTS times, or resent from the staff page
- blocked: not sent on purpose (a placeholder example.com address, or TEST_MODE without TEST_RECIPIENT)

TEST_MODE=true (the default) sends every email to TEST_RECIPIENT instead of the real staff address."""
import logging
import os
import re
import smtplib
import threading
from datetime import datetime, timedelta
from email.message import EmailMessage

from . import db

log = logging.getLogger("chatbot.notify")

MAX_ATTEMPTS = 5
RETRY_MINUTES = [1, 5, 15, 60]  # wait after the 1st, 2nd, 3rd and 4th failure
SENDING_TIMEOUT_MINUTES = 10    # a send that never finished (server stopped) is tried again after this
SEND_IN_BACKGROUND = True       # tests set this to False so sending happens before notify() returns

# Made-up addresses that must never receive email (example.com is used in the dummy content).
PLACEHOLDER = re.compile(r"@([a-z0-9-]+\.)*(example\.(com|org|net)|example|test|invalid|localhost)$", re.IGNORECASE)

_send_lock = threading.Lock()


def smtp_configured() -> bool:
    return bool(os.getenv("SMTP_HOST", "").strip())


def test_mode() -> bool:
    return os.getenv("TEST_MODE", "true").strip().lower() not in ("0", "false", "no")


def notify(campus: str, to: dict, subject: str, body: str, related_ref: str, kind: str,
           urgent: bool = False) -> dict:
    """Record a message to a staff role and send it. `to` is a role dict from routing.role().
    Urgent messages (safety tickets) are sent before everything else waiting in the outbox."""
    status = "pending" if smtp_configured() else "logged"
    row = db.add_outbox({
        "campus": campus, "to_role": to["role"], "to_email": to["email"], "subject": subject,
        "body": body, "related_ref": related_ref, "kind": kind, "status": status, "error": "",
        "priority": 1 if urgent else 0,
    })
    # The log gets the subject only, never personal details.
    log.info("Notification [%s] to %s: %s (%s)", kind, to["role"], subject, status)
    if status == "pending":
        _start_sending()
    return row


def _start_sending() -> None:
    if SEND_IN_BACKGROUND:
        # A slow mail server must not slow down the chat reply.
        threading.Thread(target=send_due, name="outbox-send", daemon=True).start()
    else:
        send_due()


def delivery_address(to_email: str) -> tuple[str | None, str]:
    """Where the email really goes, or (None, reason) if it must not be sent."""
    address = to_email
    if test_mode():
        address = os.getenv("TEST_RECIPIENT", "").strip()
        if not address:
            return None, "TEST_MODE is on but TEST_RECIPIENT is empty in .env"
    if PLACEHOLDER.search(address):
        return None, f"{address} is a placeholder address; email is never sent to it"
    return address, ""


def send_due(now: datetime | None = None) -> int:
    """Send pending emails and retry failed ones that are due. Urgent first, then oldest first.
    Returns how many were sent."""
    if not smtp_configured():
        return 0
    stamp = (now or datetime.now()).isoformat(timespec="seconds")
    sent = 0
    with _send_lock:
        with db.connect() as conn:
            rows = [dict(r) for r in conn.execute(
                """SELECT * FROM outbox
                   WHERE status = 'pending'
                      OR (status IN ('failed', 'sending') AND attempts < ? AND next_try_at <= ?)
                   ORDER BY priority DESC, id ASC""", (MAX_ATTEMPTS, stamp))]
        for row in rows:
            sent += _send_row(row, now or datetime.now())
    return sent


def _send_row(row: dict, now: datetime) -> int:
    address, reason = delivery_address(row["to_email"])
    if address is None:
        _set(row["id"], status="blocked", error=reason)
        log.warning("Email %s not sent: %s", row["id"], reason)
        return 0

    # Claim the row first, so a second server process does not send it as well.
    retry_claim = (now + timedelta(minutes=SENDING_TIMEOUT_MINUTES)).isoformat(timespec="seconds")
    with db.connect() as conn:
        claimed = conn.execute(
            "UPDATE outbox SET status = 'sending', next_try_at = ? WHERE id = ? AND status = ?",
            (retry_claim, row["id"], row["status"])).rowcount
    if not claimed:
        return 0

    attempts = row["attempts"] + 1
    subject = row["subject"]
    if test_mode():
        subject = f"[TEST, for {row['to_role']} <{row['to_email']}>] {subject}"
    try:
        _send_email(address, subject, row["body"])
    except Exception as e:
        error = repr(e)[:300]
        wait = RETRY_MINUTES[min(attempts - 1, len(RETRY_MINUTES) - 1)]
        _set(row["id"], status="failed", attempts=attempts, error=error,
             next_try_at=(now + timedelta(minutes=wait)).isoformat(timespec="seconds"))
        log.error("Email %s to %s failed (try %s of %s): %s", row["id"], row["to_role"], attempts, MAX_ATTEMPTS, error)
        return 0
    _set(row["id"], status="sent", attempts=attempts, error="", sent_to=address, sent_at=db.now(), next_try_at=None)
    log.info("Email %s sent to %s", row["id"], row["to_role"])
    return 1


def resend(outbox_id: int) -> dict | None:
    """Staff asked to send this email again (from the staff page). Sends it now and returns the row."""
    if db.find_one("outbox", id=outbox_id) is None:
        return None
    _set(outbox_id, status="pending", attempts=0, error="", next_try_at=None)
    send_due()
    return db.find_one("outbox", id=outbox_id)


def _set(outbox_id: int, **changes) -> None:
    sets = ", ".join(f"{k} = ?" for k in changes)
    with db.connect() as conn:
        conn.execute(f"UPDATE outbox SET {sets} WHERE id = ?", [*changes.values(), outbox_id])


def _send_email(to_address: str, subject: str, body: str) -> None:
    user = os.getenv("SMTP_USER", "").strip()
    msg = EmailMessage()
    msg["From"] = os.getenv("SMTP_FROM", "").strip() or user or "school-chatbot@localhost"
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)
    host = os.environ["SMTP_HOST"].strip()
    port = int(os.getenv("SMTP_PORT", "").strip() or 587)
    security = os.getenv("SMTP_SECURITY", "starttls").strip().lower()  # starttls, ssl or none
    smtp_class = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
    with smtp_class(host, port, timeout=20) as smtp:
        if security == "starttls":
            smtp.starttls()
        if user:
            smtp.login(user, os.getenv("SMTP_PASSWORD", ""))
        smtp.send_message(msg)
