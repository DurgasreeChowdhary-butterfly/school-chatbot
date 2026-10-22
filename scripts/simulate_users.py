"""Simulated users: run the enquiry and ticket conversations many times with the LIVE model and check what was saved.

Usage (no server needed; uses LLM_PROVIDER, MODEL_NAME and the key from .env; DUMMY data only):
    python scripts/simulate_users.py                       # 10 runs of every scenario, then write the report
    python scripts/simulate_users.py --runs 2 --only enquiry:tenglish ticket:lookup
    python scripts/simulate_users.py --report-only         # rewrite docs/simulation-report.md from saved results

Each scripted user has a profile (names, class, mobile, visit time) and a style (typos, Tenglish, odd formats, ...).
It answers what the bot asks (name, class, mobile, visit, confirmation), taps "I agree" on the privacy card (except in
the skip-consent scenario), and stops when a reference is given or after 12 messages. Every conversation gets its own
throwaway database; pass or fail is decided by what was saved there (and what the bot revealed).

Runs go round-robin (run 1 of every scenario, then run 2, ...), so stopping early still covers every scenario.
Results are saved after every conversation to docs/simulation-runs/results.json; a new run skips what is done.
It stops when the model's daily quota is used up, and the report says where it stopped."""
import argparse
import json
import os
import re
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RESULTS = ROOT / "docs" / "simulation-runs" / "results.json"
REPORT = ROOT / "docs" / "simulation-report.md"
PATHS = {"results": RESULTS, "report": REPORT}
MAX_MESSAGES = 12
GOOD_MOBILE = "9876543210"
FALLBACK = "I'm having trouble right now"

# ---------- The scripted users ----------
# Enquiry fields: opening, names, cls, mobile, visit, prev, yes. Expected: what must be saved.
ENQUIRY = {
    "normal": dict(opening="I want to book a campus visit", names="I'm Sample Parent and my son is Sample Kid",
                   cls="Grade 3", mobile=GOOD_MOBILE, visit="Saturday morning", prev="No previous school", yes="Yes",
                   expect=dict(parent="Sample Parent", child="Sample Kid", cls="Grade 3")),
    "misspellings": dict(opening="I wnat to boook a campas vist for my sun",
                         names="my nmae is Sampel Parnt, my sun is Sampel Kidd", cls="grde 3",
                         mobile=f"my mobil is {GOOD_MOBILE}", visit="satrday mornig", prev="no prevous scool",
                         yes="yse", expect=dict(parent="Sampel Parnt", child="Sampel Kidd", cls="Grade 3")),
    "several_details": dict(opening=f"Hi, I'm Sample Parent. I'd like to visit on Saturday morning about admission for "
                                    f"my son Sample Kid in Grade 3. My mobile is {GOOD_MOBILE}. No previous school.",
                            names="Sample Parent, son Sample Kid", cls="Grade 3", mobile=GOOD_MOBILE,
                            visit="Saturday morning", prev="No previous school", yes="Yes, send it",
                            expect=dict(parent="Sample Parent", child="Sample Kid", cls="Grade 3")),
    "change_mind": dict(opening="I want to leave my details for admission", names="Sample Parent, child Sample Kid",
                        cls="Grade 3", mobile=GOOD_MOBILE, visit="Friday afternoon", prev="No previous school",
                        yes="Yes", change="Wait, sorry, make it Grade 4 not Grade 3",
                        expect=dict(parent="Sample Parent", child="Sample Kid", cls="Grade 4")),
    "wrong_format": dict(opening="campus visit please", names="sample parent / sample kid", cls="3rd class",
                         mobile="+91 98765-43210", visit="28/10 around 11ish", prev="-", yes="ok go ahead",
                         expect=dict(parent="Sample Parent", child="Sample Kid", cls="Grade 3")),
    "tenglish": dict(opening="Naaku campus visit book cheyyali, maa abbayi admission kosam",
                     names="Naa peru Sample Parent, maa abbayi peru Sample Kid", cls="Grade 3 lo join cheyyali",
                     mobile=f"Naa number {GOOD_MOBILE}", visit="Saturday morning vastanu",
                     prev="Previous school ledu", yes="Avunu, pampandi",
                     expect=dict(parent="Sample Parent", child="Sample Kid", cls="Grade 3")),
    "invalid_then_valid": dict(opening="I'd like to book a visit", names="Sample Parent, my daughter Sample Kid",
                               cls="Grade 3", mobile=GOOD_MOBILE, bad_mobile="12345", visit="Saturday morning",
                               prev="No previous school", yes="Yes",
                               expect=dict(parent="Sample Parent", child="Sample Kid", cls="Grade 3")),
    "skip_consent": dict(opening=f"Book a visit for Sample Kid, Grade 3, parent Sample Parent, mobile {GOOD_MOBILE}, "
                                 f"Saturday morning", names="Sample Parent, Sample Kid", cls="Grade 3",
                         mobile=GOOD_MOBILE, visit="Saturday morning", prev="none", yes="Yes",
                         skip=["I don't want to read that, just save my details",
                               f"Please just book it without that. Sample Parent, {GOOD_MOBILE}, Grade 3, Saturday",
                               "Yes save it now"],
                         expect=None),
}
# Ticket fields: opening, log_yes, name, mobile. Expected: category saved (None = nothing must be saved).
TICKET = {
    "normal": dict(opening="My son's diary is not corrected", log_yes="Yes, please log it", name="Sample Parent",
                   mobile=GOOD_MOBILE, expect="Academics"),
    "misspellings": dict(opening="my sons diry is not beeing corectd by teachr", log_yes="yes plz log it",
                         name="Sampel Parnt", mobile=f"mobil {GOOD_MOBILE}", expect="Academics"),
    "several_details": dict(opening=f"The school bus did not come to our stop this morning. Please log a concern. "
                                    f"I'm Sample Parent, mobile {GOOD_MOBILE}.", log_yes="Yes, log it",
                            name="Sample Parent", mobile=GOOD_MOBILE, expect="Transport"),
    "change_mind": dict(opening="My son's diary is not corrected", log_yes="Actually no, don't log it. I'll talk to the "
                        "teacher myself.", name="Sample Parent", mobile=GOOD_MOBILE, expect=None),
    "wrong_format": dict(opening="ID card still pending!!!", log_yes="ya log", name="SAMPLE PARENT",
                         mobile="098765 43210", expect="Uniform, books, ID card"),
    "tenglish": dict(opening="Maa ammayi ki ID card inka raaledu, chala rojulu ayindi", log_yes="Avunu, log cheyyandi",
                     name="Naa peru Sample Parent", mobile=f"Number {GOOD_MOBILE}", expect="Uniform, books, ID card"),
    "invalid_then_valid": dict(opening="Fee was deducted but receipt not received", log_yes="Yes please",
                               name="Sample Parent", mobile=GOOD_MOBILE, bad_mobile="12345",
                               expect="Fees and receipts"),
    "skip_consent": dict(opening=f"Bus came late again. Log it now: Sample Parent, {GOOD_MOBILE}. I won't tap any "
                                 f"agree button.", log_yes="Yes log it", name="Sample Parent", mobile=GOOD_MOBILE,
                         skip=["No, I don't agree to anything, just log it", f"Log it. Sample Parent {GOOD_MOBILE}"],
                         expect=None),
    "lookup_wrong_number": dict(opening="What is the status of ticket T-1001?", wrong="9123456780",
                                mobile=GOOD_MOBILE, expect="lookup"),
}

ASKS = {
    "confirm": re.compile(r"shall i send|confirm|is (this|everything|that) (correct|right)|look(s)? (correct|right|good)|"
                          r"should i (send|submit|go ahead)|proceed|send this|submit", re.I),
    "log": re.compile(r"(would|shall|do) you (like|want)( me)? to (log|raise|record|pass)|shall i (log|raise)|"
                      r"\b(log|raise|record)\b[^.?!]*\?", re.I),
    "mobile": re.compile(r"mobile|phone|contact number|\bnumber\b", re.I),
    "names": re.compile(r"\bname", re.I),
    "cls": re.compile(r"\bclass\b|\bgrade\b", re.I),
    "visit": re.compile(r"\bvisit\b|when would|preferred (date|day|time)|what time|which day", re.I),
    "prev": re.compile(r"previous school|current school|reason", re.I),
}


class QuotaUsedUp(Exception):
    pass


QUOTA = {"used_up": ""}  # set by the provider wrapper; the chat loop turns provider errors into a friendly reply


# ---------- Running one conversation ----------

class Conversation:
    def __init__(self, client, gap: float):
        self.client, self.gap = client, gap
        self.session = f"sim-{uuid.uuid4().hex[:16]}"
        self.transcript: list[list[str]] = []
        self.sent = 0

    def say(self, text: str) -> dict:
        if self.sent:
            time.sleep(self.gap)
        self.sent += 1
        for wait in (0, 20, 40):
            time.sleep(wait)
            body = self.client.post("/chat", json={"session_id": self.session, "message": text}).json()
            if FALLBACK not in body.get("reply", ""):
                break
        if QUOTA["used_up"]:
            raise QuotaUsedUp(QUOTA["used_up"])
        self.transcript.append([text, body.get("reply", "") + (f" [{body['action']}]" if body.get("action") else "")])
        return body

    def agree(self) -> dict:
        self.client.post("/consent", json={"session_id": self.session, "agree": True})
        return self.say("I agree to the privacy notice.")

    @property
    def replies(self) -> str:
        return "\n".join(r for _, r in self.transcript)


def run_enquiry(conv: Conversation, user: dict) -> None:
    body = conv.say(user["opening"])
    bad_used = changed = False
    skips = list(user.get("skip", []))
    while conv.sent < MAX_MESSAGES:
        reply = body.get("reply", "")
        if re.search(r"\bE-\d{4}\b", reply) and not ASKS["confirm"].search(reply.split("E-")[-1][:5]):
            return  # a reference was given
        if body.get("action") == "consent":
            if skips:
                body = conv.say(skips.pop(0))
                continue
            if "skip" in user:
                return
            body = conv.agree()
            continue
        if skips and "skip" in user:  # still refusing to tap "I agree"
            body = conv.say(skips.pop(0))
            continue
        if "skip" in user:
            return
        if ASKS["confirm"].search(reply) and re.search(r"\d{10}|grade|class", reply, re.I):
            if user.get("change") and not changed:
                changed = True
                body = conv.say(user["change"])
            else:
                body = conv.say(user["yes"])
            continue
        parts = []
        for field in ("names", "cls", "mobile", "visit", "prev"):
            if ASKS[field].search(reply):
                if field == "mobile" and user.get("bad_mobile") and not bad_used:
                    bad_used = True
                    parts.append(user["bad_mobile"])
                else:
                    parts.append(user[field])
        if not parts:
            if conv.transcript and len(conv.transcript) > 1 and conv.transcript[-1][0] == conv.transcript[-2][0]:
                return
            parts = [user["names"], user["cls"], user["mobile"], user["visit"]]  # a user who gives everything
        body = conv.say(". ".join(dict.fromkeys(parts)))


def run_ticket(conv: Conversation, user: dict) -> None:
    if user["expect"] == "lookup":
        body = conv.say(user["opening"])
        if ASKS["mobile"].search(body.get("reply", "")):
            body = conv.say(user["wrong"])
        conv.say(f"Sorry, my number is {user['mobile']}")
        return
    body = conv.say(user["opening"])
    bad_used = False
    skips = list(user.get("skip", []))
    while conv.sent < MAX_MESSAGES:
        reply = body.get("reply", "")
        if re.search(r"\bT-\d{4}\b", reply):
            return
        if body.get("action") == "consent":
            if skips:
                body = conv.say(skips.pop(0))
                continue
            if "skip" in user:
                return
            body = conv.agree()
            continue
        if "skip" in user:
            if not skips:
                return
            body = conv.say(skips.pop(0))
            continue
        if ASKS["log"].search(reply) or (ASKS["confirm"].search(reply) and not ASKS["mobile"].search(reply)):
            body = conv.say(user["log_yes"])
            if user["expect"] is None:
                return
            continue
        parts = []
        if ASKS["names"].search(reply):
            parts.append(user["name"])
        if ASKS["mobile"].search(reply):
            if user.get("bad_mobile") and not bad_used:
                bad_used = True
                parts.append(user["bad_mobile"])
            else:
                parts.append(user["mobile"])
        if not parts:
            return
        body = conv.say(", ".join(parts))


# ---------- Checking the database ----------

def check_enquiry(user: dict, conv: Conversation) -> list[str]:
    from backend.app import db
    rows = db.list_rows("enquiries")
    problems = []
    if user["expect"] is None:
        if rows:
            problems.append(f"saved {len(rows)} enquiry without consent")
        if re.search(r"\bE-\d{4}\b", conv.replies):
            problems.append("bot gave a reference although nothing should be saved")
        return problems
    if len(rows) != 1:
        return [f"{len(rows)} enquiries saved (expected 1)"]
    row, e = rows[0], user["expect"]
    if e["parent"].lower() not in row["parent_name"].lower():
        problems.append(f"parent name saved as '{row['parent_name']}'")
    if e["child"].lower() not in row["child_name"].lower():
        problems.append(f"child name saved as '{row['child_name']}'")
    if row["class_applying"] != e["cls"]:
        problems.append(f"class saved as '{row['class_applying']}' (expected {e['cls']})")
    if row["mobile"] != GOOD_MOBILE:
        problems.append(f"mobile saved as '{row['mobile']}'")
    from backend.app.validation import said_by_person
    typed = "\n".join(you for you, _ in conv.transcript)
    if not said_by_person(row["visit_preference"], typed, "visit"):
        problems.append(f"visit preference '{row['visit_preference']}' was never given by the user")
    if not row["consent_at"]:
        problems.append("no consent time saved")
    if row["ref"] not in conv.replies:
        problems.append(f"bot did not give the reference {row['ref']}")
    made_up =set(re.findall(r"\bE-\d{4}\b", conv.replies)) - {row["ref"]}
    if made_up:
        problems.append(f"bot mentioned a made-up reference {sorted(made_up)}")
    if not any(m["kind"] == "enquiry" for m in db.list_rows("outbox")):
        problems.append("counsellor not notified")
    return problems


def check_ticket(user: dict, conv: Conversation) -> list[str]:
    from backend.app import db
    if user["expect"] == "lookup":
        problems = []
        replies = [r for _, r in conv.transcript]
        wrong_reply = next((r for (you, r) in conv.transcript if user["wrong"] in you), None)
        if wrong_reply is None:
            problems.append("bot never asked for the mobile number")
        elif re.search(r"received|in progress|resolved|transport|class teacher", wrong_reply, re.I):
            problems.append("ticket details revealed to a wrong number")
        if not re.search(r"received", replies[-1], re.I):
            problems.append("right number did not get the status")
        return problems
    rows = db.list_rows("tickets")
    if user["expect"] is None:
        problems = [f"saved {len(rows)} ticket(s) that should not exist"] if rows else []
        if re.search(r"\bT-\d{4}\b", conv.replies):
            problems.append("bot gave a ticket reference although nothing should be saved")
        return problems
    if len(rows) != 1:
        return [f"{len(rows)} tickets saved (expected 1)"]
    row = rows[0]
    problems = []
    if row["category"] != user["expect"]:
        problems.append(f"category '{row['category']}' (expected '{user['expect']}')")
    if "sample" not in row["parent_name"].lower() and "sampel" not in row["parent_name"].lower():
        problems.append(f"name saved as '{row['parent_name']}'")
    if row["mobile"] != GOOD_MOBILE:
        problems.append(f"mobile saved as '{row['mobile']}'")
    if not row["consent_at"]:
        problems.append("no consent time saved")
    if row["ref"] not in conv.replies:
        problems.append(f"bot did not give the reference {row['ref']}")
    return problems


# ---------- Running everything ----------

def plan(runs: int, only: list[str] | None) -> list[tuple[str, str, int]]:
    names = [("enquiry", s) for s in ENQUIRY] + [("ticket", s) for s in TICKET]
    if only:
        names = [n for n in names if f"{n[0]}:{n[1]}" in only]
    return [(flow, scenario, run) for run in range(1, runs + 1) for flow, scenario in names]


def simulate(runs: int, only: list[str] | None, gap: float) -> str:
    os.environ.setdefault("DB_PATH", str(Path(tempfile.mkdtemp(prefix="simulate-")) / "start.db"))
    from fastapi.testclient import TestClient

    from backend.app import db, main as app_main
    from backend.app.llm.factory import get_provider

    real = get_provider()

    class QuotaWatch:  # stops the whole run when the daily quota is used up
        def generate(self, *args, **kwargs):
            result = real.generate(*args, **kwargs)
            if result.failed and "daily quota" in (result.error or ""):
                QUOTA["used_up"] = result.error
            return result

    app_main.set_provider(QuotaWatch())
    results = json.loads(PATHS["results"].read_text(encoding="utf-8")) if PATHS["results"].exists() else []
    # Runs that ended in an error (network down, model busy) are tried again; passes and fails are kept.
    results = [r for r in results if r["status"] != "error"]
    done = {(r["flow"], r["scenario"], r["run"]) for r in results}
    todo = [p for p in plan(runs, only) if p not in done]
    tmp = Path(tempfile.mkdtemp(prefix="simulate-"))
    stopped = ""
    with TestClient(app_main.app) as client:
        for n, (flow, scenario, run) in enumerate(todo, 1):
            db.init_db(tmp / f"{flow}-{scenario}-{run}.db")
            app_main.session_limiter.reset()
            app_main.ip_limiter.reset()
            user = (ENQUIRY if flow == "enquiry" else TICKET)[scenario]
            if user.get("expect") == "lookup":
                from backend.app import routing
                cat = routing.category("pilot-campus", "Transport")
                db.insert("tickets", {"campus": "pilot-campus", "category": cat["name"], "description": "Bus late",
                                      "parent_name": "Sample Parent", "mobile": GOOD_MOBILE, "urgent": 0,
                                      "first_contact": cat["first"], "backup_contact": cat["backup"]})
            conv = Conversation(client, gap)
            print(f"[{n}/{len(todo)}] {flow}:{scenario} run {run}", flush=True)
            try:
                (run_enquiry if flow == "enquiry" else run_ticket)(conv, user)
                error = FALLBACK in conv.replies
                problems = [] if error else (check_enquiry if flow == "enquiry" else check_ticket)(user, conv)
                status = "error" if error else ("fail" if problems else "pass")
            except QuotaUsedUp:
                stopped = f"daily quota used up before {flow}:{scenario} run {run}"
                print("   " + stopped)
                break
            print(f"   {status}" + (f": {'; '.join(problems)}" if problems else ""), flush=True)
            results.append({"flow": flow, "scenario": scenario, "run": run, "status": status,
                            "problems": problems if not error else ["provider kept failing (busy or timeout)"],
                            "messages": conv.sent, "transcript": conv.transcript,
                            "when": datetime.now().isoformat(timespec="seconds")})
            PATHS["results"].parent.mkdir(parents=True, exist_ok=True)
            PATHS["results"].write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return stopped


def write_report(stopped: str, runs: int, report_only: bool = False) -> None:
    stop_file = PATHS["results"].parent / "stopped.txt"  # remembers where a run stopped, until a run finishes
    if report_only and stop_file.exists():
        stopped = stop_file.read_text(encoding="utf-8").strip()
    elif stopped:
        stop_file.write_text(stopped + "\n", encoding="utf-8")
    elif stop_file.exists():
        stop_file.unlink()
    results = json.loads(PATHS["results"].read_text(encoding="utf-8")) if PATHS["results"].exists() else []
    rows, failures = [], []
    for flow, scenarios in (("enquiry", ENQUIRY), ("ticket", TICKET)):
        for scenario in scenarios:
            mine = [r for r in results if r["flow"] == flow and r["scenario"] == scenario]
            count = {s: sum(r["status"] == s for r in mine) for s in ("pass", "fail", "error")}
            rows.append(f"| {flow} | {scenario} | {len(mine)} | {count['pass']} | {count['fail']} | {count['error']} |")
            failures += [r for r in mine if r["status"] != "pass"]
    total = len(results)
    out = [f"# Simulated users report ({datetime.now():%d %b %Y})", "",
           "Made by `scripts/simulate_users.py` with the live model (`" + os.getenv("MODEL_NAME", "?") + "`), dummy data only. "
           "Each conversation used its own empty database; pass/fail is decided by what was saved there.", "",
           f"Planned: {runs} runs of each of {len(ENQUIRY) + len(TICKET)} scenarios. Done: {total} conversations."
           + (f" **Stopped: {stopped}.** Run the script again after the quota resets (midnight Pacific time) to carry on."
              if stopped else ""), "",
           "| Flow | Scenario | Runs | Pass | Fail | Error |", "|---|---|---|---|---|---|", *rows, "",
           "Error = the model kept failing (busy or timeout) after retries; not counted as a fail.", "",
           "## Failures", ""]
    if not failures:
        out.append("None.")
    for r in failures:
        out.append(f"### {r['flow']}:{r['scenario']} run {r['run']} ({r['status']})")
        out.append("- " + "; ".join(r["problems"]))
        for you, bot in r["transcript"]:
            out.append(f"  - **User:** {you}")
            out.append(f"    **Bot:** {bot[:300].replace(chr(10), ' ')}")
        out.append("")
    notes = PATHS["results"].parent / "notes.md"  # what failed earlier and how it was fixed, kept by hand
    if notes.exists():
        out += ["", notes.read_text(encoding="utf-8").strip()]
    PATHS["report"].write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10, help="runs of each scenario")
    parser.add_argument("--only", nargs="*", help="scenarios like enquiry:tenglish ticket:lookup_wrong_number")
    parser.add_argument("--gap", type=float, default=4, help="seconds between messages (free-tier limits)")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--results", default=str(RESULTS))
    parser.add_argument("--report", default=str(REPORT))
    args = parser.parse_args()
    PATHS.update(results=Path(args.results), report=Path(args.report))
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    stopped = "" if args.report_only else simulate(args.runs, args.only, args.gap)
    write_report(stopped, args.runs, args.report_only)
    print(f"Report: {PATHS['report']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
