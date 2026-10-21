"""Enquiry capture: validation, confirmation, duplicates, routing, outbox and reminders (FakeLLM only)."""
from datetime import datetime

from backend.app import db, jobs, routing
from backend.app.validation import clean_name, mask_mobile, normalize_mobile
from tests.conftest import chat, tool_turn

DETAILS = {
    "parent_name": "Sample Parent",
    "child_name": "Sample Child",
    "class_applying": "Grade 3",
    "mobile": "+91 98765 43210",
    "previous_school": "Old School",
    "reason": "Moving house",
    "visit_preference": "Saturday morning",
}


def submit_and_confirm(client, fake, details=DETAILS, session_id="s1"):
    [checked] = tool_turn(client, fake, "here are my details", ("submit_enquiry", details), session_id=session_id)
    [saved] = tool_turn(client, fake, "yes, that's right", ("confirm_enquiry", {}), session_id=session_id)
    return checked, saved


# ---------- Validation ----------

def test_mobile_numbers():
    assert normalize_mobile("9876543210") == "9876543210"
    assert normalize_mobile("+91 98765-43210") == "9876543210"
    assert normalize_mobile("919876543210") == "9876543210"
    assert normalize_mobile("09876543210") == "9876543210"
    assert normalize_mobile("12345") is None
    assert normalize_mobile("5876543210") is None  # Indian mobiles start with 6-9
    assert normalize_mobile("98765432101") is None
    assert mask_mobile("9876543210") == "98******10"


def test_names():
    assert clean_name("  Ravi   Kumar ") == "Ravi Kumar"
    assert clean_name("D'Souza-Rao") == "D'Souza-Rao"
    assert clean_name("R") is None
    assert clean_name("Ravi123") is None


# ---------- Enquiry flow ----------

def test_enquiry_is_saved_after_confirmation(client, fake):
    checked, saved = submit_and_confirm(client, fake)
    assert checked["status"] == "needs_confirmation"
    assert checked["summary"]["mobile"] == "9876543210"
    assert saved["status"] == "saved" and saved["ref"] == "E-1001"

    [row] = db.list_rows("enquiries")
    assert row["status"] == "New"
    assert row["assigned_to"] == "Admission counsellor"
    assert row["class_applying"] == "Grade 3"

    [mail] = db.list_rows("outbox")
    assert mail["to_email"] == "admissions.campusa@example.com"
    assert mail["status"] == "logged"  # no SMTP settings in tests
    assert "E-1001" in mail["subject"]


def test_enquiry_tools_are_offered_to_the_ai(client, fake):
    chat(client, "hello")
    names = {t.name for t in fake.calls[0]["tools"]}
    assert {"submit_enquiry", "confirm_enquiry"} <= names
    submit = next(t for t in fake.calls[0]["tools"] if t.name == "submit_enquiry")
    assert submit.parameters["properties"]["class_applying"]["enum"] == routing.classes("pilot-campus")


def test_cannot_confirm_in_the_same_turn_as_submit(client, fake):
    checked, confirmed = tool_turn(client, fake, "details", ("submit_enquiry", DETAILS), ("confirm_enquiry", {}))
    assert checked["status"] == "needs_confirmation"
    assert "not confirmed yet" in confirmed["error"]
    assert db.list_rows("enquiries") == []


def test_resubmitting_the_same_details_then_confirming_works(client, fake):
    """Seen live: on "yes" the AI checked the same details again, then confirmed in one turn."""
    tool_turn(client, fake, "details", ("submit_enquiry", DETAILS))
    checked, saved = tool_turn(client, fake, "yes", ("submit_enquiry", DETAILS), ("confirm_enquiry", {}))
    assert saved["status"] == "saved"


def test_changed_details_need_a_new_confirmation(client, fake):
    tool_turn(client, fake, "details", ("submit_enquiry", DETAILS))
    changed = {**DETAILS, "class_applying": "Grade 4"}
    _, saved = tool_turn(client, fake, "make it grade 4 and save", ("submit_enquiry", changed), ("confirm_enquiry", {}))
    assert "not confirmed yet" in saved["error"]
    [saved] = tool_turn(client, fake, "yes", ("confirm_enquiry", {}))
    assert saved["status"] == "saved"
    assert db.list_rows("enquiries")[0]["class_applying"] == "Grade 4"


def test_cannot_confirm_without_submit(client, fake):
    [result] = tool_turn(client, fake, "yes", ("confirm_enquiry", {}))
    assert "submit_enquiry first" in result["error"]
    assert db.list_rows("enquiries") == []


def test_invalid_details_are_rejected(client, fake):
    bad = {**DETAILS, "mobile": "12345", "class_applying": "Grade 12", "parent_name": "R2D2"}
    [result] = tool_turn(client, fake, "details", ("submit_enquiry", bad))
    assert set(result["problems"]) == {"mobile", "class_applying", "parent_name"}
    [after] = tool_turn(client, fake, "yes", ("confirm_enquiry", {}))
    assert "error" in after
    assert db.list_rows("enquiries") == []


def test_missing_required_details_are_rejected(client, fake):
    [result] = tool_turn(client, fake, "details", ("submit_enquiry", {"parent_name": "Sample Parent"}))
    assert {"child_name", "class_applying", "mobile", "visit_preference"} <= set(result["problems"])


def test_duplicate_mobile_adds_a_note_instead_of_a_new_enquiry(client, fake):
    submit_and_confirm(client, fake, session_id="first")
    again = {**DETAILS, "child_name": "Second Child", "mobile": "9876543210"}
    _, saved = submit_and_confirm(client, fake, again, session_id="second")
    assert saved["status"] == "already_registered" and saved["ref"] == "E-1001"
    [row] = db.list_rows("enquiries")
    assert "Repeat enquiry" in row["notes"] and "Second Child" in row["notes"]
    assert len(db.list_rows("outbox")) == 2


def test_counsellor_email_can_be_overridden_in_env(client, fake, monkeypatch):
    monkeypatch.setenv("COUNSELLOR_EMAIL_PILOT", "counsellor@example.org")
    submit_and_confirm(client, fake)
    assert db.list_rows("outbox")[0]["to_email"] == "counsellor@example.org"


# ---------- Reminders ----------

def make_enquiry(created_at: str, status="New"):
    row = db.insert("enquiries", {**{k: v for k, v in DETAILS.items()}, "mobile": "9876543210",
                                  "campus": "pilot-campus", "assigned_to": "Admission counsellor"})
    db.update("enquiries", row["ref"], created_at=created_at, status=status)
    return row["ref"]


def test_working_days_skip_weekends():
    friday = datetime(2026, 10, 23, 10, 0)
    assert jobs.add_working_days(friday, 1) == datetime(2026, 10, 26, 10, 0)  # Monday
    assert jobs.add_working_days(friday, 2) == datetime(2026, 10, 27, 10, 0)


def test_enquiry_reminder_then_escalation(client):
    make_enquiry("2026-10-19T10:00:00")  # a Monday
    assert jobs.run_reminders(datetime(2026, 10, 20, 9, 0)) == 0      # not yet 1 working day
    assert jobs.run_reminders(datetime(2026, 10, 20, 10, 0)) == 1     # reminder to counsellor
    assert jobs.run_reminders(datetime(2026, 10, 20, 12, 0)) == 0     # not repeated
    assert jobs.run_reminders(datetime(2026, 10, 21, 10, 0)) == 1     # escalate to front office
    assert jobs.run_reminders(datetime(2026, 10, 25, 10, 0)) == 0
    kinds = [(m["kind"], m["to_role"]) for m in reversed(db.list_rows("outbox"))]
    assert kinds == [("reminder", "Admission counsellor"), ("escalation", "Front office")]


def test_no_reminder_once_contacted(client):
    make_enquiry("2026-10-19T10:00:00", status="Contacted")
    assert jobs.run_reminders(datetime(2026, 10, 30, 10, 0)) == 0
