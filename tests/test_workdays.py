"""Working days from config/working_days.json: Saturdays, holidays, and reminder deadlines that use them."""
import json
from datetime import date, datetime

import pytest

from backend.app import db, jobs, routing, workdays
from backend.app.knowledge import KB_DIR


def cal(**data):
    return workdays.parse({"week": "Monday to Saturday", **data})


def test_only_first_and_third_saturdays_are_working_days():
    c = workdays.load()
    assert workdays.is_working_day(date(2026, 11, 7), c)        # 1st Saturday of November
    assert not workdays.is_working_day(date(2026, 11, 14), c)   # 2nd
    assert workdays.is_working_day(date(2026, 11, 21), c)       # 3rd
    assert not workdays.is_working_day(date(2026, 10, 31), c)   # 5th
    assert not workdays.is_working_day(date(2026, 11, 1), c)    # Sunday


def test_holidays_are_skipped():
    friday = datetime(2026, 11, 6, 10, 0)
    assert workdays.add_working_days(friday, 1) == datetime(2026, 11, 7, 10, 0)   # 1st Saturday
    assert workdays.add_working_days(friday, 2) == datetime(2026, 11, 12, 10, 0)  # Sunday + Diwali 8-11 Nov skipped
    assert not workdays.is_working_day(date(2026, 12, 25))                        # one-day holiday (no "to")


def test_monday_to_friday_and_every_saturday_settings():
    friday = datetime(2026, 10, 30, 10, 0)
    five_day = workdays.parse({"week": "Monday to Friday"})
    every_saturday = cal(working_saturdays="all")
    assert workdays.add_working_days(friday, 1, five_day) == datetime(2026, 11, 2, 10, 0)
    assert workdays.add_working_days(friday, 1, every_saturday) == datetime(2026, 10, 31, 10, 0)


@pytest.mark.parametrize("data, message", [
    ({"week": "Every day"}, "'week' must be one of"),
    ({"week": "Monday to Saturday", "working_saturdays": [6]}, "working_saturdays"),
    ({"week": "Monday to Saturday", "holidays": [{"name": "X", "from": "8 Nov 2026"}]}, "YYYY-MM-DD"),
    ({"week": "Monday to Saturday", "holidays": [{"name": "X", "from": "2026-11-08", "to": "2026-11-01"}]}, "ends before"),
])
def test_mistakes_in_the_file_give_a_clear_message(data, message):
    with pytest.raises(ValueError, match=message):
        workdays.parse(data)


def test_config_holidays_match_calendar_md():
    """config/working_days.json must list the same holidays as kb/pilot-campus/calendar.md."""
    in_calendar = workdays.holidays_in_calendar((KB_DIR / "pilot-campus" / "calendar.md").read_text(encoding="utf-8"))
    in_config = json.loads(workdays.CONFIG_FILE.read_text(encoding="utf-8"))["holidays"]
    assert [h["name"] for h in in_calendar] == [h["name"] for h in in_config]
    for written, configured in zip(in_calendar, in_config):
        assert written["from"] == configured["from"], written["name"]
        if written["to"]:  # "from 1 May" has no end date in calendar.md
            assert written["to"] == configured.get("to", configured["from"]), written["name"]


def test_reminder_waits_for_the_holidays_to_end(client):
    # Logged on Saturday 17 Oct 2026 (3rd Saturday, a working day); 19-21 Oct is Dussehra.
    row = db.insert("enquiries", {"campus": "pilot-campus", "parent_name": "Sample Parent", "child_name": "Sample Child",
                                  "class_applying": "Grade 3", "mobile": "9876543210", "visit_preference": "Any",
                                  "assigned_to": "Admission counsellor"})
    db.update("enquiries", row["ref"], created_at="2026-10-17T10:00:00")
    assert jobs.run_reminders(datetime(2026, 10, 21, 18, 0)) == 0   # Sunday and the holidays don't count
    assert jobs.run_reminders(datetime(2026, 10, 22, 10, 0)) == 1   # Thursday: first working day after
    assert db.list_rows("outbox")[0]["kind"] == "reminder"


def test_ticket_escalation_skips_non_working_saturday_and_holidays():
    cat = routing.category("pilot-campus", "Transport")
    row = db.insert("tickets", {"campus": "pilot-campus", "category": cat["name"], "description": "x",
                                "parent_name": "Sample Parent", "mobile": "9876543210", "urgent": 0,
                                "first_contact": cat["first"], "backup_contact": cat["backup"]})
    db.update("tickets", row["ref"], created_at="2026-11-05T10:00:00", status="In progress")  # Thursday
    # 3 working days: Fri 6, Sat 7 (1st Saturday), then Thu 12 (8-11 Nov is Diwali)
    assert jobs.run_reminders(datetime(2026, 11, 11, 23, 0)) == 0
    assert jobs.run_reminders(datetime(2026, 11, 12, 10, 0)) == 1
    assert db.list_rows("outbox")[0]["kind"] == "escalation"
