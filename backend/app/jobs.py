"""Reminder and escalation job. Runs every 15 minutes in the background, and can be run
by hand from the staff page. The same background thread sends pending emails and retries failed ones every minute.
Deadlines count working days from config/working_days.json (weekends, non-working Saturdays and holidays skipped)."""
import logging
import threading
from datetime import datetime

from . import db, routing
from .workdays import add_working_days
from .notify import notify, send_due

log = logging.getLogger("chatbot.jobs")
INTERVAL_SECONDS = 15 * 60  # reminders and escalations
EMAIL_RETRY_SECONDS = 60    # pending and failed emails


def is_due(created_at: str, days: int, now: datetime) -> bool:
    return now >= add_working_days(datetime.fromisoformat(created_at), days)


def run_reminders(now: datetime | None = None) -> int:
    """Create due reminders and escalations. Returns how many notifications were made."""
    now = now or datetime.now()
    made = 0

    for e in db.list_rows("enquiries"):
        if e["status"] != "New":
            continue
        campus = e["campus"]
        if not e["reminded_at"] and is_due(e["created_at"], routing.deadline(campus, "enquiry_reminder"), now):
            notify(campus, routing.counsellor(campus), f"Reminder: enquiry {e['ref']} not yet contacted",
                   _enquiry_text(e), e["ref"], "reminder")
            db.update("enquiries", e["ref"], reminded_at=db.now())
            made += 1
        if not e["escalated_at"] and is_due(e["created_at"], routing.deadline(campus, "enquiry_escalation"), now):
            notify(campus, routing.front_office(campus), f"Escalation: enquiry {e['ref']} still not contacted",
                   _enquiry_text(e), e["ref"], "escalation")
            db.update("enquiries", e["ref"], escalated_at=db.now())
            made += 1

    for t in db.list_rows("tickets"):
        if t["status"] == "Resolved":
            continue
        campus = t["campus"]
        if (t["status"] == "Received" and not t["reminded_at"]
                and is_due(t["created_at"], routing.deadline(campus, "ticket_acknowledge"), now)):
            notify(campus, routing.role(campus, t["first_contact"]),
                   f"Reminder: please acknowledge ticket {t['ref']}", _ticket_text(t), t["ref"], "reminder",
                   urgent=bool(t["urgent"]))
            db.update("tickets", t["ref"], reminded_at=db.now())
            made += 1
        if not t["escalated_at"] and is_due(t["created_at"], routing.deadline(campus, "ticket_escalation"), now):
            notify(campus, routing.role(campus, t["backup_contact"]),
                   f"Escalation: ticket {t['ref']} not resolved", _ticket_text(t), t["ref"], "escalation",
                   urgent=bool(t["urgent"]))
            db.update("tickets", t["ref"], escalated_at=db.now())
            made += 1

    if made:
        log.info("Reminder job made %s notification(s)", made)
    return made


def _enquiry_text(e: dict) -> str:
    return (f"Enquiry {e['ref']} ({e['campus']})\nParent: {e['parent_name']}\nChild: {e['child_name']} "
            f"({e['class_applying']})\nMobile: {e['mobile']}\nVisit preference: {e['visit_preference']}\n"
            f"Logged: {e['created_at']}\nStatus: {e['status']}")


def _ticket_text(t: dict) -> str:
    return (f"Ticket {t['ref']} ({t['campus']}){' URGENT' if t['urgent'] else ''}\nCategory: {t['category']}\n"
            f"Concern: {t['description']}\nParent: {t['parent_name']}\nMobile: {t['mobile']}\n"
            f"Logged: {t['created_at']}\nStatus: {t['status']}")


def start_background_job(stop: threading.Event) -> threading.Thread:
    def loop():
        ticks_per_reminder_run = INTERVAL_SECONDS // EMAIL_RETRY_SECONDS
        tick = 0
        while not stop.wait(EMAIL_RETRY_SECONDS):
            tick += 1
            if tick % ticks_per_reminder_run == 0:
                try:
                    run_reminders()
                except Exception:
                    log.exception("Reminder job failed")
            try:
                send_due()
            except Exception:
                log.exception("Sending emails failed")
    thread = threading.Thread(target=loop, name="reminder-job", daemon=True)
    thread.start()
    return thread
