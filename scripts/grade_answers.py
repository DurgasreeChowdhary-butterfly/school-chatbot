"""Automatic pass/fail checks for answer-quality runs, using docs/test-checks.json.

Usage: python scripts/grade_answers.py docs/test-runs/latest.json [more runs ...]

Each answer is "pass", "fail" (with the reasons) or "error" (the bot gave its fallback reply,
usually because the model's quota was used up or it timed out). The checks catch missing facts and
obvious mistakes; a person should still read the answers now and then (python scripts/show_results.py)."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKS_FILE = ROOT / "docs" / "test-checks.json"
FALLBACK = "I'm having trouble right now"
CONSENT_MARK = "[chat window shows: consent]"


def load_checks(path: Path = CHECKS_FILE) -> dict:
    return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if not k.startswith("_")}


def grade(reply: str, check: dict | None) -> tuple[str, list[str]]:
    """Return ("pass" | "fail" | "error" | "unchecked", reasons)."""
    if FALLBACK in reply:
        return "error", ["fallback reply (quota, timeout or provider error)"]
    if check is None:
        return "unchecked", ["no checks for this question"]
    reasons = []
    for alternatives in check.get("all", []):
        if not any(re.search(p, reply, re.IGNORECASE) for p in alternatives):
            reasons.append("missing: " + " / ".join(alternatives))
    for pattern in check.get("none", []):
        if re.search(pattern, reply, re.IGNORECASE):
            reasons.append("should not say: " + pattern)
    if "consent" in check:
        shown = CONSENT_MARK in reply
        if check["consent"] and not shown:
            reasons.append("privacy notice not shown")
        if not check["consent"] and shown:
            reasons.append("asked for consent instead of answering")
    return ("fail" if reasons else "pass"), reasons


def grade_run(results: list[dict], checks: dict | None = None) -> dict[str, tuple[str, list[str]]]:
    checks = load_checks() if checks is None else checks
    return {r["id"]: grade(r["reply"], checks.get(str(r["id"]))) for r in results}


def main() -> None:
    checks = load_checks()
    for name in sys.argv[1:]:
        results = json.loads(Path(name).read_text(encoding="utf-8"))
        graded = grade_run(results, checks)
        counts = {k: sum(1 for v, _ in graded.values() if v == k) for k in ("pass", "fail", "error", "unchecked")}
        print(f"{name}: {counts['pass']} pass, {counts['fail']} fail, {counts['error']} error"
              + (f", {counts['unchecked']} unchecked" if counts["unchecked"] else ""))
        for qid, (verdict, reasons) in graded.items():
            if verdict != "pass":
                print(f"   [{qid}] {verdict}: {'; '.join(reasons)}")


if __name__ == "__main__":
    main()
