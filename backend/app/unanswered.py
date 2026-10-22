"""Questions the bot could not answer from the knowledge files (it said it doesn't have that information).
The staff page lists them with counts, so the school can see which information is missing.
Phone numbers, emails and Aadhaar-like numbers are removed before anything is stored. Question text is never logged."""
import re
from datetime import datetime

from . import db

# How the rules tell the bot to say it does not know (prompts.py, rule 1).
DONT_KNOW = re.compile(
    r"\bi (?:don't|do not|didn't|did not) have (?:that|this|the|any|information|details|specific|exact|a |an )|"
    r"\bi'?m not sure\b|\bi am not sure\b|\bnot (?:in|part of) (?:my|the) (?:information|knowledge)\b|"
    r"\bno information (?:on|about)\b", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
NUMBER = re.compile(r"(?:\+?\d[\d\s-]{6,}\d)")  # phone, Aadhaar or any long number
MAX_CHARS = 300


# Refusals and policy answers that use the same words but are not missing information.
NOT_A_GAP = re.compile(r"\b(?:authority|permission|comparison|compare|personal information|other discounts?|"
                       r"any other discounts?|per-child|specific child|your child's)\b", re.I)


def is_unanswered(reply: str) -> bool:
    """True when a sentence of the reply says the information is not available (and is not a refusal)."""
    for sentence in re.split(r"(?<=[.!?])\s+", reply or ""):
        if DONT_KNOW.search(sentence) and not NOT_A_GAP.search(sentence):
            return True
    return False


def clean(question: str) -> str:
    text = EMAIL.sub("[email]", question or "")
    text = NUMBER.sub("[number]", text)
    return " ".join(text.split())[:MAX_CHARS]


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9\[\] ]+", "", text.lower()).strip()


def record(campus: str, question: str) -> None:
    text = clean(question)
    key = _key(text)
    if len(key) < 3:
        return
    stamp = datetime.now().isoformat(timespec="microseconds")  # exact order, even within one second
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM unanswered WHERE campus = ? AND key = ?", (campus, key)).fetchone()
        if row:
            # Asked again: count it, and show it again if staff had marked the content as added.
            conn.execute("UPDATE unanswered SET count = count + 1, last_at = ?, question = ?, status = 'open' "
                         "WHERE id = ?", (stamp, text, row["id"]))
        else:
            conn.execute("INSERT INTO unanswered (campus, question, key, count, first_at, last_at, status) "
                         "VALUES (?, ?, ?, 1, ?, ?, 'open')", (campus, text, key, stamp, stamp))


def open_questions(limit: int = 200) -> list[dict]:
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, campus, question, count, first_at, last_at FROM unanswered WHERE status = 'open' "
            "ORDER BY last_at DESC, id DESC LIMIT ?", (limit,))]


def mark_content_added(question_id: int) -> bool:
    with db.connect() as conn:
        return conn.execute("UPDATE unanswered SET status = 'content_added', handled_at = ? WHERE id = ?",
                            (db.now(), question_id)).rowcount > 0
