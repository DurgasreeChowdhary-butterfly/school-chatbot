"""Check the knowledge files before going live (for the day the dummy files are replaced with the school's real ones).

Usage:
    python scripts/check_kb.py                       # checks kb/ and config/, DEMO_MODE from .env
    python scripts/check_kb.py --live                # check as if DEMO_MODE=false
    python scripts/check_kb.py --kb path/to/new/kb   # check a folder of new files before copying them into kb/

It checks that every required file exists with the expected headings, that routing.json and
config/working_days.json agree with escalation.md and calendar.md, and, when DEMO_MODE=false, that no file
still contains the word DUMMY, an example.com address or a "+91 00000" phone number.
Prints a checklist. Exit code 0 = ready, 1 = something to fix."""
import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from backend.app.workdays import holidays_in_calendar, parse as parse_working_days  # noqa: E402

# Required files in every campus folder and the headings each must have (the start of the heading line).
# Headings are structure, not school facts: the real files must keep them.
REQUIRED = {
    "admissions.md": ["# Admissions", "## Process", "## Age criteria", "## Classes offered", "## Admission test"],
    "documents.md": ["# Documents required"],
    "fees.md": ["# Fee structure"],
    "discounts_policy.md": ["# Discounts"],
    "curriculum.md": ["# Curriculum"],
    "calendar.md": ["# Academic calendar"],
    "ptm.md": ["# Parent-teacher meetings"],
    "transport.md": ["# Transport"],
    "contacts.md": ["# Campus contacts"],
    "registration.md": ["# Registration"],
    "hiring.md": ["# Hiring"],
    "faq.md": ["# Frequently asked questions"],
    "escalation.md": ["# Who handles which concern"],
    "privacy_notice.md": ["# Privacy notice"],
}
# Lines the bot and the code rely on, inside some files.
REQUIRED_LINES = {
    "contacts.md": ["Office hours", "Front office phone", "Admission counsellor"],
    "calendar.md": ["Holidays:"],
}
ROUTING_KEYS = ["classes", "counsellor", "front_office", "roles", "categories", "deadlines_in_working_days"]
DEADLINES = ["enquiry_reminder", "enquiry_escalation", "ticket_acknowledge", "ticket_escalation"]

DEMO_PATTERNS = {
    "the word DUMMY": re.compile(r"\bdummy\b", re.IGNORECASE),
    "an example.com address": re.compile(r"[\w.+-]+@([\w-]+\.)*example\.com\b", re.IGNORECASE),
    'a "+91 00000" phone number': re.compile(r"\+91[\s-]*00000"),
}


@dataclass
class Check:
    ok: bool
    item: str
    detail: str = ""


def check_all(kb: Path, config_dir: Path, demo_mode: bool) -> list[Check]:
    results: list[Check] = []
    add = lambda ok, item, detail="": results.append(Check(ok, item, detail))  # noqa: E731

    # School file and campus folders
    school_file = kb / "school.json"
    campuses = []
    try:
        school = json.loads(school_file.read_text(encoding="utf-8"))
        campuses = [c["id"] for c in school["campuses"]]
        add(bool(school.get("school_name")) and bool(campuses), "school.json: school name and campuses",
            f"{school.get('school_name', '?')}, {len(campuses)} campus(es)")
    except FileNotFoundError:
        add(False, "school.json", "file missing")
    except (ValueError, KeyError, TypeError) as e:
        add(False, "school.json", f"not valid: {e}")

    for campus in campuses:
        folder = kb / campus
        if not folder.is_dir():
            add(False, f"{campus}/", "campus folder missing (every campus in school.json needs one)")
            continue
        for name, headings in REQUIRED.items():
            path = folder / name
            if not path.exists():
                add(False, f"{campus}/{name}", "file missing")
                continue
            lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
            missing = [h for h in headings if not any(line.lower().startswith(h.lower()) for line in lines)]
            missing += [f'a line with "{t}"' for t in REQUIRED_LINES.get(name, [])
                        if not any(t.lower() in line.lower() for line in lines)]
            add(not missing, f"{campus}/{name}", "missing: " + "; ".join(missing) if missing else "headings OK")
        results.extend(_check_routing(folder, campus))
        results.extend(_check_calendar(folder, campus, config_dir))

    # Leftover demo content
    files = sorted(p for p in [*kb.rglob("*.md"), *kb.rglob("*.json"), *config_dir.glob("*.json")] if p.is_file())
    found = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        hits = [label for label, pattern in DEMO_PATTERNS.items() if pattern.search(text)]
        if hits:
            base = kb.parent if path.is_relative_to(kb) else config_dir.parent
            found.append(f"{path.relative_to(base).as_posix()}: {', '.join(hits)}")
    if demo_mode:
        add(True, "Demo content", f"{len(found)} file(s) still have dummy content (allowed while DEMO_MODE=true)")
    elif found:
        for line in found:
            add(False, "Demo content left", line)
    else:
        add(True, "Demo content", "no DUMMY, example.com or +91 00000 found")
    return results


def _check_routing(folder: Path, campus: str) -> list[Check]:
    item = f"{campus}/routing.json"
    try:
        routing = json.loads((folder / "routing.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [Check(False, item, "file missing")]
    except ValueError as e:
        return [Check(False, item, f"not valid JSON: {e}")]
    problems = [f"key '{k}' missing" for k in ROUTING_KEYS if k not in routing]
    if problems:
        return [Check(False, item, "; ".join(problems))]
    roles = routing["roles"]
    for key in ("counsellor", "front_office"):
        if routing[key] not in roles:
            problems.append(f"{key} '{routing[key]}' is not in roles")
    for c in routing["categories"]:
        for who in (c.get("first"), c.get("backup")):
            if who not in roles:
                problems.append(f"category '{c.get('name')}' uses '{who}', which is not in roles")
    problems += [f"deadline '{d}' missing" for d in DEADLINES if d not in routing["deadlines_in_working_days"]]
    problems += [f"role '{r}' has no email" for r, info in roles.items() if not info.get("email")]
    # The categories must be the same as the table in escalation.md
    escalation = folder / "escalation.md"
    if escalation.exists():
        table = set()
        for line in escalation.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if line.strip().startswith("|") and len(cells) == 3 and cells[0] not in ("Category", "") \
                    and not set(cells[0]) <= set("-: "):
                table.add(cells[0])
        routed = {c.get("name") for c in routing["categories"]}
        if table != routed:
            problems.append(f"categories differ from escalation.md (only in escalation.md: {sorted(table - routed)}; "
                            f"only in routing.json: {sorted(routed - table)})")
    return [Check(not problems, item, "; ".join(problems) if problems else
                  f"{len(routing['categories'])} categories, {len(roles)} roles, agrees with escalation.md")]


def _check_calendar(folder: Path, campus: str, config_dir: Path) -> list[Check]:
    item = "config/working_days.json"
    path = config_dir / "working_days.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        parse_working_days(data)
    except FileNotFoundError:
        return [Check(False, item, "file missing")]
    except ValueError as e:
        return [Check(False, item, f"not valid: {e}")]
    calendar = folder / "calendar.md"
    if not calendar.exists():
        return [Check(True, item, "valid (no calendar.md to compare with)")]
    written = holidays_in_calendar(calendar.read_text(encoding="utf-8"))
    if not written:
        return [Check(False, item, f"could not read the holidays in {campus}/calendar.md: write them like "
                                   "'Holidays: Diwali 8 to 11 November 2026. Christmas 25 December 2026.'")]
    configured = {h.get("name"): h for h in data.get("holidays", [])}
    problems = []
    for h in written:
        c = configured.get(h["name"])
        if c is None:
            problems.append(f"'{h['name']}' is in calendar.md but not in working_days.json")
        elif c["from"] != h["from"] or (h["to"] and c.get("to", c["from"]) != h["to"]):
            problems.append(f"'{h['name']}' dates differ from calendar.md ({h['from']} to {h['to'] or '?'})")
    problems += [f"'{n}' is in working_days.json but not in calendar.md"
                 for n in configured if n not in {h["name"] for h in written}]
    return [Check(not problems, item, "; ".join(problems) if problems else
                  f"valid, {len(written)} holidays agree with {campus}/calendar.md")]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb", default=str(ROOT / "kb"), help="knowledge folder to check")
    parser.add_argument("--config", default=str(ROOT / "config"), help="config folder (working_days.json)")
    parser.add_argument("--live", action="store_true", help="check as if DEMO_MODE=false")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    demo_mode = not args.live and os.getenv("DEMO_MODE", "true").strip().lower() in ("1", "true", "yes")
    results = check_all(Path(args.kb), Path(args.config), demo_mode)

    print(f"Knowledge files check: {args.kb}  (DEMO_MODE={'true' if demo_mode else 'false'})\n")
    for r in results:
        print(f"  [{'x' if r.ok else ' '}] {'OK  ' if r.ok else 'FIX '} {r.item}" + (f": {r.detail}" if r.detail else ""))
    problems = sum(not r.ok for r in results)
    print()
    if problems:
        print(f"{problems} thing(s) to fix. Fix them, then run this again.")
    else:
        print("All checks passed." + ("" if not demo_mode else
                                       " Demo content is allowed because DEMO_MODE=true; run with --live before going live."))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
