"""Concern tickets, status lookup (including wrong numbers), urgent safety tickets, callbacks
and ticket escalation (FakeLLM only)."""
from datetime import datetime

from backend.app import db, jobs, routing
from backend.app.knowledge import KB_DIR
from backend.app.ticket_tools import MAX_FAILED_LOOKUPS
from tests.conftest import tool_turn

DIARY = {"category": "Academics", "description": "My son's diary is not corrected",
         "parent_name": "Sample Parent", "mobile": "9876543210"}


def new_ticket(client, fake, details=DIARY, session_id="s1"):
    [result] = tool_turn(client, fake, "please log it", ("create_ticket", details), session_id=session_id)
    return result


def lookup(client, fake, ref, mobile, session_id="lookup"):
    [result] = tool_turn(client, fake, "status?", ("get_ticket_status", {"ticket_ref": ref, "mobile": mobile}),
                         session_id=session_id)
    return result


def test_routing_file_matches_escalation_md():
    """routing.json must say the same as kb/pilot-campus/escalation.md."""
    table = {}
    for line in (KB_DIR / "pilot-campus" / "escalation.md").read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 3 and cells[0] not in ("Category", "---"):
            table[cells[0]] = cells
    routed = {c["name"]: c for c in routing.categories("pilot-campus")}
    assert set(table) == set(routed)
    for name, (_, first, backup) in table.items():
        assert first.startswith(routed[name]["first"]), name
        assert backup == routed[name]["backup"], name
    assert [c["name"] for c in routing.categories("pilot-campus") if c.get("urgent")] == ["Safety, health, bullying"]


def test_ticket_is_routed_by_category(client, fake):
    result = new_ticket(client, fake)
    assert result["status"] == "created" and result["ref"] == "T-1001" and result["urgent"] is False
    [row] = db.list_rows("tickets")
    assert (row["status"], row["first_contact"], row["backup_contact"]) == ("Received", "Class teacher", "Coordinator")
    [mail] = db.list_rows("outbox")
    assert mail["to_role"] == "Class teacher" and "T-1001" in mail["subject"]


def test_ticket_details_are_validated(client, fake):
    bad = {"category": "Cafeteria", "description": "", "parent_name": "123", "mobile": "12345"}
    result = new_ticket(client, fake, bad)
    assert set(result["problems"]) == {"category", "description", "parent_name", "mobile"}
    assert db.list_rows("tickets") == []


def test_safety_ticket_is_urgent_and_alerts_people_at_once(client, fake):
    safety = {**DIARY, "category": "Safety, health, bullying", "description": "My child is being bullied"}
    result = new_ticket(client, fake, safety)
    assert result["urgent"] is True
    assert "call the front office now" in result["message"]
    assert routing.front_office("pilot-campus")["phone"] in result["message"]
    roles = sorted(m["to_role"] for m in db.list_rows("outbox"))
    assert roles == ["Front office", "Principal", "Vice principal"]
    assert all("URGENT" in m["subject"] for m in db.list_rows("outbox"))


def test_status_lookup_with_the_right_mobile(client, fake):
    new_ticket(client, fake)
    result = lookup(client, fake, "t-1001", "+91 98765 43210")
    assert result["status"] == "Received" and result["handled_by"] == "Class teacher"
    db.update("tickets", "T-1001", status="In progress")
    assert lookup(client, fake, "T-1001", "9876543210")["status"] == "In progress"


def test_status_lookup_with_a_wrong_mobile_reveals_nothing(client, fake):
    new_ticket(client, fake)
    wrong = lookup(client, fake, "T-1001", "9123456789")
    missing = lookup(client, fake, "T-9999", "9876543210")
    assert wrong == missing == {"status": "no_match", "message": wrong["message"]}
    assert "Academics" not in str(wrong) and "Sample Parent" not in str(wrong)


def test_status_lookups_lock_after_too_many_failures(client, fake):
    new_ticket(client, fake)
    for _ in range(MAX_FAILED_LOOKUPS):
        lookup(client, fake, "T-1001", "9123456789", session_id="guesser")
    # Even the right number is refused in that session now.
    assert "Too many attempts" in lookup(client, fake, "T-1001", "9876543210", session_id="guesser")["error"]
    assert lookup(client, fake, "T-1001", "9876543210", session_id="someone-else")["status"] == "Received"


def test_callback_request(client, fake):
    [result] = tool_turn(client, fake, "call me", ("request_callback", {"name": "Sample Parent", "mobile": "9876543210"}))
    assert result["ref"] == "C-1001"
    [row] = db.list_rows("callbacks")
    assert row["assigned_to"] == "Front office" and row["status"] == "New"
    assert db.list_rows("outbox")[0]["to_role"] == "Front office"


def test_callback_needs_a_valid_mobile(client, fake):
    [result] = tool_turn(client, fake, "call me", ("request_callback", {"name": "Sample Parent", "mobile": "555"}))
    assert "mobile" in result["problems"]
    assert db.list_rows("callbacks") == []


def test_ticket_tools_are_offered_with_categories_from_routing(client, fake):
    tool_turn(client, fake, "hi", ("get_ticket_status", {"ticket_ref": "T-1", "mobile": "x"}))
    spec = next(t for t in fake.calls[0]["tools"] if t.name == "create_ticket")
    assert spec.parameters["properties"]["category"]["enum"] == [c["name"] for c in routing.categories("pilot-campus")]


# ---------- Escalation job ----------

def make_ticket(created_at: str, status="Received", category="Transport"):
    cat = routing.category("pilot-campus", category)
    row = db.insert("tickets", {"campus": "pilot-campus", "category": cat["name"], "description": "x",
                                "parent_name": "Sample Parent", "mobile": "9876543210", "urgent": 0,
                                "first_contact": cat["first"], "backup_contact": cat["backup"]})
    db.update("tickets", row["ref"], created_at=created_at, status=status)


def test_ticket_acknowledge_reminder_then_escalation_to_backup():
    make_ticket("2026-10-26T10:00:00")  # Monday
    assert jobs.run_reminders(datetime(2026, 10, 27, 9, 59)) == 0
    assert jobs.run_reminders(datetime(2026, 10, 27, 10, 0)) == 1   # 1 working day: remind first contact
    assert jobs.run_reminders(datetime(2026, 10, 29, 9, 0)) == 0
    assert jobs.run_reminders(datetime(2026, 10, 29, 10, 0)) == 1   # 3 working days: escalate to backup
    assert jobs.run_reminders(datetime(2026, 11, 6, 10, 0)) == 0
    sent = [(m["kind"], m["to_role"]) for m in reversed(db.list_rows("outbox"))]
    assert sent == [("reminder", "Transport coordinator"), ("escalation", "Principal")]


def test_acknowledged_ticket_gets_no_reminder_but_still_escalates():
    make_ticket("2026-10-26T10:00:00", status="In progress")
    assert jobs.run_reminders(datetime(2026, 10, 27, 10, 0)) == 0
    assert jobs.run_reminders(datetime(2026, 10, 29, 10, 0)) == 1


def test_resolved_ticket_is_left_alone():
    make_ticket("2026-10-01T10:00:00", status="Resolved")
    assert jobs.run_reminders(datetime(2026, 11, 6, 10, 0)) == 0
