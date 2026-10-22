"""Enquiry tools: the AI collects admission enquiry details, the backend validates,
asks for confirmation, detects duplicates by mobile number, saves and notifies the counsellor."""
import logging

from . import db, routing
from .llm.base import ToolSpec
from .notify import notify
from .validation import clean_name, clean_text, made_up, match_choice, mask_mobile, normalize_mobile

log = logging.getLogger("chatbot.enquiries")


def specs(campus: str) -> list[ToolSpec]:
    """Classes come from kb/<campus>/routing.json."""
    return [
        ToolSpec(
            name="submit_enquiry",
            description=(
                "Check an admission enquiry or campus visit request once you have all the details. "
                "Does NOT save it: it returns a summary to show the person for confirmation, "
                "or a list of problems to ask about again."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "parent_name": {"type": "string", "description": "Parent or guardian's name"},
                    "child_name": {"type": "string", "description": "Child's name"},
                    "class_applying": {"type": "string", "enum": routing.classes(campus)},
                    "mobile": {"type": "string", "description": "10-digit Indian mobile number, exactly as typed"},
                    "previous_school": {"type": "string", "description": "Optional: previous school"},
                    "reason": {"type": "string", "description": "Optional: reason for changing school"},
                    "visit_preference": {"type": "string", "description": "When they would like to visit, or 'No visit for now'"},
                },
                "required": ["parent_name", "child_name", "class_applying", "mobile", "visit_preference"],
            },
        ),
        ToolSpec(
            name="confirm_enquiry",
            description=(
                "Save the enquiry checked by submit_enquiry. Call this ONLY after the person has seen the "
                "summary and said yes in a later message."
            ),
            parameters={"type": "object", "properties": {}},
        ),
    ]



def submit_enquiry(args: dict, ctx) -> dict:
    problems = {}
    parent = clean_name(args.get("parent_name"))
    child = clean_name(args.get("child_name"))
    cls = match_choice(args.get("class_applying"), routing.classes(ctx.campus))
    mobile = normalize_mobile(args.get("mobile"))
    previous = clean_text(args.get("previous_school"), 120)
    reason = clean_text(args.get("reason"), 200)
    visit = clean_text(args.get("visit_preference"), 100, required=True)
    if not parent:
        problems["parent_name"] = "Please ask for the parent or guardian's name (letters only)."
    if not child:
        problems["child_name"] = "Please ask for the child's name (letters only)."
    if not cls:
        problems["class_applying"] = "Class must be one of: " + ", ".join(routing.classes(ctx.campus))
    if not mobile:
        problems["mobile"] = "Not a valid 10-digit Indian mobile number. Ask the person to type it again."
    if previous is None:
        problems["previous_school"] = "Too long. Ask for a shorter answer."
    if reason is None:
        problems["reason"] = "Too long. Ask for a shorter answer."
    if not visit:
        problems["visit_preference"] = "Ask when they would like to visit the campus (or no visit for now)."
    if not problems:
        problems = made_up({"parent_name": (parent, "text"), "child_name": (child, "text"), "class_applying": (cls, "class"),
                            "mobile": (mobile, "mobile"), "visit_preference": (visit, "visit"),
                            "previous_school": (previous, "optional"), "reason": (reason, "optional")}, ctx.said)
    if problems:
        ctx.session.pending_enquiry = None
        return {"error": "Some details need fixing. Ask the person about these only.", "problems": problems}

    details = {
        "parent_name": parent, "child_name": child, "class_applying": cls, "mobile": mobile,
        "previous_school": previous, "reason": reason, "visit_preference": visit,
    }
    pending = ctx.session.pending_enquiry
    if pending and pending["details"] == details:
        # Same details as the summary the person already saw: keep the original turn,
        # so their "yes" can be confirmed even if the AI checks the details once more.
        pass
    else:
        ctx.session.pending_enquiry = {"details": details, "turn": ctx.session.turn}
    return {
        "status": "needs_confirmation",
        "summary": details,
        "instruction": "Show these details to the person and ask them to confirm. Wait for their reply. "
                       "Only if they say yes, call confirm_enquiry. If they want changes, call submit_enquiry again.",
    }


def confirm_enquiry(args: dict, ctx) -> dict:
    pending = ctx.session.pending_enquiry
    if not pending:
        return {"error": "There is no checked enquiry. Collect the details and call submit_enquiry first."}
    if pending["turn"] == ctx.session.turn:
        # The person has not had a chance to reply to the summary yet.
        return {"error": "The person has not confirmed yet. Show the summary and wait for their reply."}

    d = pending["details"]
    campus = ctx.campus
    counsellor = routing.counsellor(campus)
    ctx.session.pending_enquiry = None

    existing = db.find_one("enquiries", campus=campus, mobile=d["mobile"])
    if existing:
        note = (f"[{db.now()}] Repeat enquiry via chat: {d['child_name']} ({d['class_applying']}), "
                f"visit: {d['visit_preference']}")
        notes = (existing["notes"] + "\n" + note).strip()
        db.update("enquiries", existing["ref"], notes=notes)
        notify(campus, routing.role(campus, existing["assigned_to"]),
               f"Repeat enquiry on {existing['ref']}", note, existing["ref"], "enquiry")
        log.info("Duplicate enquiry for %s added to %s", mask_mobile(d["mobile"]), existing["ref"])
        return {
            "status": "already_registered",
            "ref": existing["ref"],
            "message": "We already have an enquiry from this mobile number, so a note was added to it "
                       "instead of creating a new one. Tell the person the reference.",
        }

    row = db.insert("enquiries", {**d, "campus": campus, "assigned_to": counsellor["role"],
                                  "consent_at": ctx.session.consent_at})
    notify(campus, counsellor, f"New enquiry {row['ref']}: {d['class_applying']}",
           _enquiry_body(row), row["ref"], "enquiry")
    log.info("Enquiry %s saved for %s", row["ref"], mask_mobile(d["mobile"]))
    return {
        "status": "saved",
        "ref": row["ref"],
        "assigned_to": f"{counsellor['name']} ({counsellor['role']})",
        "message": "Tell the person their reference and that the admission counsellor will contact them.",
    }


def _enquiry_body(e: dict) -> str:
    return (f"Enquiry {e['ref']} ({e['campus']})\nParent: {e['parent_name']}\nChild: {e['child_name']} "
            f"({e['class_applying']})\nMobile: {e['mobile']}\nPrevious school: {e['previous_school'] or '-'}\n"
            f"Reason: {e['reason'] or '-'}\nVisit preference: {e['visit_preference']}")


HANDLERS = {
    "submit_enquiry": submit_enquiry,
    "confirm_enquiry": confirm_enquiry,
}
