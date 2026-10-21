"""Notifications to staff. Every notification is written to the outbox table and the log.
Real email is sent only when SMTP_HOST, SMTP_USER and SMTP_PASSWORD are set in .env."""
import logging
import os
import smtplib
from email.message import EmailMessage

from . import db

log = logging.getLogger("chatbot.notify")


def smtp_configured() -> bool:
    return all(os.getenv(k, "").strip() for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"))


def notify(campus: str, to: dict, subject: str, body: str, related_ref: str, kind: str) -> dict:
    """Send (or just record) a message to a staff role. `to` is a role dict from routing.role()."""
    status, error = "logged", ""
    if smtp_configured():
        try:
            _send_email(to["email"], subject, body)
            status = "sent"
        except Exception as e:
            status, error = "failed", repr(e)[:300]
            log.error("Email to %s failed: %s", to["role"], error)
    row = db.add_outbox({
        "campus": campus, "to_role": to["role"], "to_email": to["email"], "subject": subject,
        "body": body, "related_ref": related_ref, "kind": kind, "status": status, "error": error,
    })
    # The log gets the subject only, never personal details.
    log.info("Notification [%s] to %s: %s (%s)", kind, to["role"], subject, status)
    return row


def _send_email(to_address: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = os.getenv("SMTP_FROM", "").strip() or os.environ["SMTP_USER"]
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)
    port = int(os.getenv("SMTP_PORT", "587") or 587)
    with smtplib.SMTP(os.environ["SMTP_HOST"], port, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(msg)
