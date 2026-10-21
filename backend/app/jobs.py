"""Reminder and escalation job. Runs every 15 minutes in the background, and can be run
by hand from the staff page. Working days are Monday to Friday (school holidays are not counted yet)."""
import logging
import threading
from datetime import datetime, timedelta

from . import db, routing
from .notify import notify

log = logging.getLogger("chatbot.jobs")
INTERVAL_SECONDS = 15 * 60


def add_working_days(start: datetime, days: int) -> datetime:
    """The moment `days` working days after `start` (Saturdays and Sundays skipped)."""
    moment = start
    while days > 0:
        moment += timedelta(days=1)
        if moment.weekday() < 5:  # Monday=0 ... Friday=4
            days -= 1
    return moment


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
                   f"Reminder: please acknowledge ticket {t['ref']}", _ticket_text(t), t["ref"], "reminder")
            db.update("tickets", t["ref"], reminded_at=db.now())
            made += 1
        if not t["escalated_at"] and is_due(t["created_at"], routing.deadline(campus, "ticket_escalation"), now):
            notify(campus, routing.role(campus, t["backup_contact"]),
                   f"Escalation: ticket {t['ref']} not resolved", _ticket_text(t), t["ref"], "escalation")
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
        while not stop.wait(INTERVAL_SECONDS):
            try:
                run_reminders()
            except Exception:
                log.exception("Reminder job failed")
    thread = threading.Thread(target=loop, name="reminder-job", daemon=True)
    thread.start()
    return thread
