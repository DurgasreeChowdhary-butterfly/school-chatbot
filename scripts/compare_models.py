"""Run the 40-question answer-quality test for several models and print a table of pass counts.

Usage (no server needed; uses LLM_PROVIDER and the API key from .env):
    python scripts/compare_models.py gemini-3.5-flash-lite gemini-3.1-flash-lite
    python scripts/compare_models.py gemini-3.5-flash-lite --only 5 6 25 --gap 8

Each model first gets one tiny test request. A model whose daily quota is used up (or that does not answer)
is skipped, so no quota is wasted. A model that hits its quota part-way through is stopped after
3 failed replies in a row and marked "stopped". Answers are saved to docs/test-runs/compare-<model>.json
and checked with scripts/grade_answers.py (docs/test-checks.json). Uses a throwaway database.
Dummy data only: never run this with real parent or child data on the free tier."""
import argparse
import csv
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
# A throwaway database, set before the app is imported.
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="compare-models-")) / "compare.db")

from fastapi.testclient import TestClient  # noqa: E402

from backend.app import main as app_main  # noqa: E402
from backend.app.llm.base import Message  # noqa: E402
from backend.app.llm.factory import get_provider  # noqa: E402
from grade_answers import FALLBACK, grade_run  # noqa: E402


def probe(provider) -> str | None:
    """One tiny request. Returns None if the model answers, or the reason it can't be used."""
    result = provider.generate("Reply with the single word OK.", [Message(role="user", content="Hello")])
    if not result.failed:
        return None
    if "daily quota" in (result.error or ""):
        return "daily quota used up"
    return (result.error or "no answer")[:120]


def run_model(client: TestClient, model: str, questions: list[dict], gap: float) -> tuple[list[dict], bool]:
    """Ask every question in a new chat session. Returns (answers, stopped_early)."""
    results, fails_in_a_row = [], 0
    out = ROOT / "docs" / "test-runs" / f"compare-{model}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    for i, q in enumerate(questions):
        if i:
            time.sleep(gap)
        r = client.post("/chat", json={"session_id": f"compare-{uuid.uuid4().hex[:12]}", "message": q["question"]})
        body = r.json()
        reply = body.get("reply", f"HTTP {r.status_code}")
        if body.get("action"):
            reply += f" [chat window shows: {body['action']}]"
        print(f"   [{q['id']}] {reply[:100]!r}")
        results.append({**q, "model": model, "reply": reply})
        out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        fails_in_a_row = fails_in_a_row + 1 if FALLBACK in reply else 0
        if fails_in_a_row >= 3:
            print("   stopping this model: 3 failed replies in a row (probably its quota)")
            return results, True
    return results, False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="+", help="model names, e.g. gemini-3.5-flash-lite")
    parser.add_argument("--only", nargs="*", type=int, help="question ids to run")
    parser.add_argument("--gap", type=float, default=6, help="seconds between questions (free-tier limits)")
    args = parser.parse_args()

    with open(ROOT / "docs" / "test-questions.csv", encoding="utf-8") as f:
        questions = [r for r in csv.DictReader(f) if not args.only or int(r["id"]) in args.only]

    table = []
    with TestClient(app_main.app) as client:
        for model in args.models:
            print(f"== {model}")
            try:
                provider = get_provider(model)
            except Exception as e:
                table.append((model, "-", "-", "-", f"skipped: {e}"))
                continue
            reason = probe(provider)
            if reason:
                print(f"   skipped: {reason}")
                table.append((model, "-", "-", "-", f"skipped: {reason}"))
                continue
            app_main.set_provider(provider)
            app_main.session_limiter.reset()
            app_main.ip_limiter.reset()
            results, stopped = run_model(client, model, questions, args.gap)
            verdicts = [v for v, _ in grade_run(results).values()]
            status = f"stopped after {len(results)} of {len(questions)}" if stopped else "complete"
            table.append((model, verdicts.count("pass"), verdicts.count("fail"), verdicts.count("error"), status))

    print()
    print(f"| Model | Pass (of {len(questions)}) | Fail | Error | Run |")
    print("|---|---|---|---|---|")
    for row in table:
        print("| " + " | ".join(str(c) for c in row) + " |")


if __name__ == "__main__":
    main()
