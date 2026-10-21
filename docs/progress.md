# Progress log

## Stage A: /chat answers correctly (21 Oct 2026)

**Built**
- Chat loop (`backend/app/chat_service.py`) that can run tools the AI asks for, with a limit of 4 tool rounds.
- Neutral messages that can carry tool calls and tool results (`llm/base.py`), and Gemini conversion for them.
- FakeLLM (`llm/fake_provider.py`) for automated tests; `LLM_PROVIDER=fake` also works.
- Retry with backoff in the Gemini provider (429 and 5xx; not for timeouts or a used-up daily quota).
- In-memory sessions (`sessions.py`), settings in one place (`config.py`).
- Answer-quality runner `scripts/run_test_questions.py` (new session per question, spaced calls, retries,
  saves after every answer, stops after 3 failures in a row) and `scripts/show_results.py`.
- Clearer rules in `prompts.py`.

**Tested**
- pytest: 12 tests (health, chat, prompt contents, history cap, provider failure and exception, tool loop, Gemini conversion,
  only `llm/` imports SDKs). All pass.
- Live: all 40 questions, then two improvement rounds. See `docs/test-report.md`: 34 pass, 6 need Stage C/D tools.

**What failed and how it was fixed**
- `gemini-3.8-flash` timed out (504) on every call, even a 3-word prompt. Switched to `gemini-3.6-flash`.
- `gemini-3.6-flash` free tier allows only 20 requests per day, used up in the first run (429 "PerDay" quota).
  Switched to `gemini-3.5-flash-lite`, which handled all runs. The first run's answers were lost when it was stopped,
  so the runner now saves after every question.
- Weak answers (age comparison, concern routing, invalid phone, partial answers) fixed with general rules in `prompts.py`.

**Still weak**
- Flash-Lite is a smaller model. It follows the rules well in these tests, but may slip on unusual wording.
- The free-tier daily quota limits how often the live test can be run (about one full run plus reruns a day is safe).
- The 40 questions are judged by hand; there is no automatic scoring.
