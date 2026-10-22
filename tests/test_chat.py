"""Tests for /health, /chat, the chat loop and the provider layer (FakeLLM only)."""
import re
from pathlib import Path

from backend.app import config, main
from backend.app.chat_service import FALLBACK_REPLY
from backend.app.llm.base import LLMResult, Message, ToolCall
from tests.conftest import chat


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "demo": True, "database": "ok"}


def test_health_reports_a_broken_database(client, monkeypatch, tmp_path):
    from backend.app import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "missing-folder" / "chatbot.db")
    r = client.get("/health")
    assert r.status_code == 503 and r.json()["database"] == "error"


def test_widget_config_and_files(client):
    cfg = client.get("/config").json()
    assert cfg["demo"] is True
    assert cfg["campuses"] == [{"id": "pilot-campus", "name": "Campus A"}]
    assert "Fees" in cfg["menus"]["prospective"]
    assert client.get("/widget/chat.js").status_code == 200
    assert client.get("/widget/chat.css").status_code == 200
    assert '<script src="/widget/chat.js"' in client.get("/demo").text


def test_chat_returns_reply_and_demo_flag(client, fake):
    fake.add(LLMResult(text="Grade 1 needs 6 years as on 31 May."))
    assert chat(client, "Minimum age for Grade 1?") == {
        "reply": "Grade 1 needs 6 years as on 31 May.",
        "demo": True,
        "action": None,
        "notice": None,
    }


def test_prompt_contains_rules_knowledge_and_group(client, fake):
    chat(client, "Hi", group="existing")
    prompt = fake.calls[0]["system_prompt"]
    assert "Answer ONLY from the KNOWLEDGE section" in prompt
    assert "=== File: fees.md ===" in prompt
    assert "Rs 25,000" in prompt  # from the dummy fee table
    assert "current parent or student" in prompt


def test_history_is_kept_per_session_and_capped(client, fake, monkeypatch):
    monkeypatch.setattr(main.session_limiter, "limit", 1000)  # this test sends many messages quickly
    turns = config.HISTORY_LIMIT // 2 + 3  # more turns than the memory holds
    for i in range(turns):
        chat(client, f"message {i}", session_id="a")
    chat(client, "other session", session_id="b")
    sent_last_in_a = fake.calls[-2]["messages"]
    assert len(sent_last_in_a) == config.HISTORY_LIMIT + 1  # remembered messages + the new one
    assert sent_last_in_a[-1].content == f"message {turns - 1}"
    assert [m.content for m in fake.calls[-1]["messages"]] == ["other session"]


def test_provider_failure_returns_friendly_message(client, fake):
    fake.add(LLMResult(failed=True, error="429 rate limited"))
    assert chat(client, "Hello")["reply"] == FALLBACK_REPLY


def test_provider_exception_returns_friendly_message(client, fake):
    def boom(*args, **kwargs):
        raise RuntimeError("secret stack trace")
    fake.generate = boom
    body = chat(client, "Hello")
    assert body["reply"] == FALLBACK_REPLY
    assert "Traceback" not in str(body)


def test_failed_turn_is_not_remembered(client, fake):
    fake.add(LLMResult(failed=True, error="timeout"))
    chat(client, "first")
    chat(client, "second")
    assert [m.content for m in fake.calls[-1]["messages"]] == ["second"]


def test_unknown_campus(client):
    assert "don't have information for that campus" in chat(client, "Hi", campus="nowhere")["reply"]


def test_unknown_tool_is_reported_back_to_the_model(client, fake):
    fake.add(
        LLMResult(tool_calls=[ToolCall(name="no_such_tool", arguments={}, id="1")]),
        LLMResult(text="Sorry, I could not do that."),
    )
    assert chat(client, "do something")["reply"] == "Sorry, I could not do that."
    tool_msg = fake.calls[1]["messages"][-1]
    assert tool_msg.role == "tool" and "Unknown tool" in tool_msg.content


def test_endless_tool_calls_stop_with_friendly_message(client, fake):
    fake.add(*[LLMResult(tool_calls=[ToolCall(name="x", arguments={}, id="1")]) for _ in range(10)])
    assert chat(client, "loop")["reply"] == FALLBACK_REPLY


def test_gemini_message_conversion_handles_tool_turns():
    from backend.app.llm.gemini_provider import _to_gemini_contents
    contents = _to_gemini_contents([
        Message(role="user", content="hi"),
        Message(role="assistant", tool_calls=[ToolCall(name="t", arguments={"a": 1}, id="c1")]),
        Message(role="tool", content='{"ok": true}', tool_call_id="c1", name="t"),
        Message(role="assistant", content="done"),
    ])
    assert [c.role for c in contents] == ["user", "model", "user", "model"]
    assert contents[1].parts[0].function_call.name == "t"
    assert contents[2].parts[0].function_response.name == "t"


def test_only_llm_folder_imports_provider_sdks():
    app_dir = Path(__file__).resolve().parents[1] / "backend" / "app"
    pattern = re.compile(r"^\s*(from|import)\s+(google|anthropic|openai)\b", re.M)
    offenders = [
        str(p) for p in app_dir.rglob("*.py")
        if "llm" not in p.parts and pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_garbled_email_addresses_are_repaired(client, fake):
    """Found in the consistency test: the model once wrote hr.example.com instead of hr@example.com."""
    fake.add(LLMResult(text="Send your resume to hr.example.com or HR at example.com. Accounts: "
                            "accounts.campusa (at) example.com. Keep admissions.campusa@example.com as it is."))
    reply = chat(client, "Are you hiring?")["reply"]
    assert reply == ("Send your resume to hr@example.com or hr@example.com. Accounts: accounts.campusa@example.com. "
                     "Keep admissions.campusa@example.com as it is.")
    chat(client, "Thanks")
    assert "hr.example.com" not in fake.calls[-1]["messages"][1].content  # the repaired reply is remembered


def test_email_repair_leaves_other_text_alone():
    from backend.app.chat_service import repair_emails
    knowledge = "Email hr@example.com or accounts.campusa@example.com."
    for text in ["Visit www.example.com", "The office (hr) is open", "Write to hr@example.com"]:
        assert repair_emails(text, knowledge) == text


def test_made_up_contact_gets_one_corrected_reply(client, fake):
    """Found in the consistency test: the model invented hr.campusa@example.com."""
    fake.add(LLMResult(text="Send your resume to hr.campusa@example.com."),
             LLMResult(text="Send your resume to hr@example.com."))
    assert chat(client, "Are you hiring?")["reply"] == "Send your resume to hr@example.com."
    note = fake.calls[-1]["messages"][-1]
    assert note.role == "user" and "hr.campusa@example.com" in note.content
    chat(client, "Thanks")
    remembered = [m.content for m in fake.calls[-1]["messages"]]
    assert remembered[:2] == ["Are you hiring?", "Send your resume to hr@example.com."]  # the check is not remembered


def test_made_up_contact_twice_is_replaced_by_the_front_office(client, fake):
    fake.add(LLMResult(text="Call +91 98765 00000 or mail hr.campusa@example.com."),
             LLMResult(text="Call +91 98765 00000 or mail hr.campusa@example.com."))
    reply = chat(client, "Are you hiring?")["reply"]
    assert reply == "Call the front office (+91 00000 00001) or mail the front office (+91 00000 00001)."


def test_contacts_from_knowledge_or_the_person_need_no_check(client, fake):
    fake.add(LLMResult(text="I have your number 98765 43210. The front office is on +91 00000 00001, "
                            "and the counsellor is admissions.campusa@example.com."))
    chat(client, "My number is 9876543210")
    assert len(fake.calls) == 1
