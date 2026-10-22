"""Compare several runs of the same questions: for each question, how many runs passed.

Usage: python scripts/consistency_report.py docs/test-runs/c1.json docs/test-runs/c2.json docs/test-runs/c3.json
Prints a Markdown table (paste it into docs/consistency-report.md). Uses the checks in docs/test-checks.json."""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grade_answers import ROOT, grade_run, load_checks  # noqa: E402


def main() -> None:
    files = sys.argv[1:]
    checks = load_checks()
    runs = [grade_run(json.loads(Path(f).read_text(encoding="utf-8")), checks) for f in files]
    with open(ROOT / "docs" / "test-questions.csv", encoding="utf-8") as f:
        questions = list(csv.DictReader(f))

    print(f"| # | Question | Passed (of {len(files)}) | Notes |")
    print("|---|---|---|---|")
    totals = [0] * len(files)
    for q in questions:
        verdicts = [run.get(q["id"], ("missing", ["not run"])) for run in runs]
        passed = sum(v == "pass" for v, _ in verdicts)
        for i, (v, _) in enumerate(verdicts):
            totals[i] += v == "pass"
        notes = "; ".join(f"run {i + 1}: {v} ({', '.join(r)})" for i, (v, r) in enumerate(verdicts) if v != "pass")
        flag = "" if passed in (0, len(files)) else " (flips)"
        print(f"| {q['id']} | {q['question']} | {passed}{flag} | {notes} |")
    print()
    print("Pass count per run: " + ", ".join(f"run {i + 1}: {t}/{len(questions)}" for i, t in enumerate(totals)))


if __name__ == "__main__":
    main()
