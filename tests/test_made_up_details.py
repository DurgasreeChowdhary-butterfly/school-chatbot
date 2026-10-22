"""The backend refuses details the person never typed (found by scripts/simulate_users.py: the model saved
"No visit for now" although the visitor was never asked)."""
import json

from backend.app import db
from backend.app.llm.base import LLMResult, ToolCall
from backend.app.validation import said_by_person
from tests.conftest import agree, chat

DETAILS = {"parent_name": "Sample Parent", "child_name": "Sample Kid", "class_applying": "Grade 3",
           "mobile": "9876543210", "visit_preference": "No visit for now"}


def call(client, fake, message, name, args, session_id):
    """The visitor sends `message` (exactly as typed); the AI calls one tool. Returns the tool's result."""
    fake.add(LLMResult(tool_calls=[ToolCall(name=name, arguments=args, id="c1")]), LLMResult(text="OK"))
    chat(client, message, session_id=session_id)
    return json.loads([m for m in fake.calls[-1]["messages"] if m.role == "tool"][-1].content)


def test_visit_time_the_person_never_gave_is_refused(client, fake):
    agree(client, "v1")
    chat(client, "Sample Parent, child Sample Kid. Grade 3", session_id="v1")
    result = call(client, fake, "9876543210", "submit_enquiry", DETAILS, "v1")
    assert list(result["problems"]) == ["visit_preference"]
    assert "never fill in" in result["problems"]["visit_preference"]


def test_details_given_over_several_messages_are_accepted(client, fake):
    agree(client, "v2")
    chat(client, "I'm Sample Parent, my son is Sample Kid, grade 3", session_id="v2")
    chat(client, "my number is 98765 43210", session_id="v2")
    result = call(client, fake, "no visit for now please", "submit_enquiry", DETAILS, "v2")
    assert result["status"] == "needs_confirmation"


def test_made_up_mobile_or_name_is_refused(client, fake):
    agree(client, "v3")
    chat(client, "I'm Sample Parent, my son is Sample Kid, Grade 3, visit on Saturday", session_id="v3")
    result = call(client, fake, "ok", "submit_enquiry", {**DETAILS, "visit_preference": "Saturday"}, "v3")
    assert list(result["problems"]) == ["mobile"]
    ticket = call(client, fake, "my number is 9876543210", "create_ticket",
                  {"category": "Transport", "description": "Bus late", "parent_name": "Ravi Kumar",
                   "mobile": "9876543210"}, "v3")
    assert list(ticket["problems"]) == ["parent_name"]
    assert db.list_rows("tickets") == []


def test_how_details_are_matched():
    said = "naa peru Sampel Parnt. maa abbayi 3rd class. Number +91 98765-43210. 28/10 around 11ish. ledu"
    assert said_by_person("Sampel Parnt", said)
    assert said_by_person("Grade 3", said, "class")
    assert not said_by_person("Grade 4", said, "class")
    assert said_by_person("9876543210", said, "mobile")
    assert not said_by_person("9876543211", said, "mobile")
    assert said_by_person("28 October, around 11 am", said, "visit")
    assert said_by_person("No visit for now", said, "visit")          # "ledu" = no (Telugu)
    assert not said_by_person("No visit for now", "Sample Parent, Grade 3", "visit")
    assert not said_by_person("Saturday morning", "Sample Parent, Grade 3", "visit")
    assert said_by_person("UKG", "my daughter is in ukg", "class")


def test_small_spelling_differences_are_accepted():
    """Found by the simulated users: "satrday mornig" passed on as "Saturday morning" was refused, and the model
    then kept asking for a date."""
    said = "my nmae is Sampel Parnt. satrday mornig"
    assert said_by_person("Saturday morning", said, "visit")
    assert said_by_person("Sample Parent", said)
    assert not said_by_person("Sunday evening", said, "visit")
    assert not said_by_person("Ravi Kumar", said)
