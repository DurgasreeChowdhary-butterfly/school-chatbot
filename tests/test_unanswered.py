"""Questions the bot could not answer: recorded without numbers or emails, counted, listed for staff."""
from datetime import datetime, timedelta

from backend.app import db, retention, unanswered
from backend.app.llm.base import LLMResult
from tests.conftest import chat
from tests.test_staff import HEADERS, login

DONT_KNOW = "I don't have that information. You can contact the front office at +91 00000 00001."


def ask(client, fake, question, reply=DONT_KNOW, session="u1"):
    fake.add(LLMResult(text=reply))
    chat(client, question, session_id=session)


def test_unanswered_question_is_recorded_without_numbers_or_emails(client, fake):
    ask(client, fake, "Do you have a swimming pool? Call me on 98765 43210 or mail me@home.in")
    [q] = unanswered.open_questions()
    assert q["question"] == "Do you have a swimming pool? Call me on [number] or mail [email]"
    assert q["count"] == 1 and q["campus"] == "pilot-campus"


def test_answered_questions_and_refusals_are_not_recorded(client, fake):
    ask(client, fake, "What are the school timings?", reply="Classes run from 8:45 to 15:15.")
    ask(client, fake, "Can you give me 20 percent discount?",
        reply="I don't have the authority to offer other discounts. We offer a 5 percent sibling concession.")
    ask(client, fake, "Compare with XYZ", reply="I don't have a comparison with other schools.")
    assert unanswered.open_questions() == []


def test_same_question_is_counted_and_newest_comes_first(client, fake):
    ask(client, fake, "Do you have a swimming pool?", session="a1")
    ask(client, fake, "Is there a music room?", session="a2")
    ask(client, fake, "do you have a SWIMMING pool", session="a3")   # same question, different case
    first, second = unanswered.open_questions()
    assert first["question"] == "do you have a SWIMMING pool" and first["count"] == 2
    assert second["question"] == "Is there a music room?" and second["count"] == 1


def test_partial_answers_count_too(client, fake):
    ask(client, fake, "What is the syllabus for Grade 4?",
        reply="We follow the state board. I don't have the subject-wise list; the front office can share it.")
    assert [q["question"] for q in unanswered.open_questions()] == ["What is the syllabus for Grade 4?"]


def test_staff_see_them_and_mark_content_added(client, fake):
    ask(client, fake, "Do you have a swimming pool?")
    login(client)
    [q] = client.get("/staff/api/data").json()["unanswered"]
    assert client.post(f"/staff/api/unanswered/{q['id']}/done").status_code == 403          # header needed
    assert client.post(f"/staff/api/unanswered/{q['id']}/done", headers=HEADERS).status_code == 200
    assert client.get("/staff/api/data").json()["unanswered"] == []
    assert client.post("/staff/api/unanswered/9999/done", headers=HEADERS).status_code == 404
    ask(client, fake, "Do you have a swimming pool?", session="later")                     # asked again: back
    [again] = client.get("/staff/api/data").json()["unanswered"]
    assert again["count"] == 2


def test_list_needs_login(client):
    assert client.get("/staff/api/data").status_code == 401
    assert client.post("/staff/api/unanswered/1/done", headers=HEADERS).status_code == 401


def test_old_unanswered_questions_are_purged():
    unanswered.record("pilot-campus", "Do you have a swimming pool?")
    old = (datetime.now() - timedelta(days=400)).isoformat(timespec="seconds")
    with db.connect() as conn:
        conn.execute("UPDATE unanswered SET last_at = ?", (old,))
    assert retention.purge_old(12, apply=True) == {"unanswered": 1}
    assert unanswered.open_questions() == []


def test_question_text_is_never_logged(client, fake, caplog):
    ask(client, fake, "Do you have a secretquestionword pool?")
    assert "secretquestionword" not in caplog.text
