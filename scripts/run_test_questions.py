"""Answer-quality test: send every question in docs/test-questions.csv to a running server's /chat.

Usage (server must be running, with the live model):
    python scripts/run_test_questions.py                 # all questions
    python scripts/run_test_questions.py --only 5 6 17   # some questions
    python scripts/run_test_questions.py --out docs/test-runs/round2.json

Each question gets a new session. Calls are spaced out for free-tier rate limits,
and a fallback ("I'm having trouble") reply is retried with backoff.
The answers are saved to a JSON file; a person judges them against the "expected" column."""
import argparse
import csv
import json
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
FALLBACK = "I'm having trouble right now"
BACKOFF = [15, 30, 60]  # seconds to wait before retrying a fallback reply


def ask(base_url: str, question: str) -> str:
    for attempt in range(len(BACKOFF) + 1):
        try:
            r = httpx.post(
                f"{base_url}/chat",
                json={"session_id": f"quality-{uuid.uuid4().hex[:12]}", "message": question},
                timeout=120,
            )
            reply = r.json().get("reply", f"HTTP {r.status_code}")
        except Exception as e:
            reply = f"{FALLBACK} (client error: {e})"
        if FALLBACK not in reply or attempt == len(BACKOFF):
            return reply
        print(f"   fallback reply, retrying in {BACKOFF[attempt]}s")
        time.sleep(BACKOFF[attempt])
    return reply


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--only", nargs="*", type=int, help="question ids to run")
    parser.add_argument("--gap", type=float, default=6, help="seconds between questions")
    parser.add_argument("--out", default="docs/test-runs/latest.json")
    args = parser.parse_args()

    with open(ROOT / "docs" / "test-questions.csv", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if not args.only or int(r["id"]) in args.only]

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    results, failures_in_a_row = [], 0
    for i, row in enumerate(rows):
        if i:
            time.sleep(args.gap)
        print(f"[{row['id']}] {row['question']}")
        reply = ask(args.base_url, row["question"])
        print(f"   -> {reply[:160]!r}")
        results.append({**row, "reply": reply})
        # Save after every question, so nothing is lost if the run stops.
        out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        failures_in_a_row = failures_in_a_row + 1 if FALLBACK in reply else 0
        if failures_in_a_row >= 3:
            print("Stopping: 3 failed replies in a row (probably the daily quota). Check the server log.")
            break
    print(f"Saved {len(results)} answers to {out}")


if __name__ == "__main__":
    main()
