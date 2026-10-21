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

## Stage B: Chat window (21 Oct 2026)

**Built**
- `widget/chat.js` and `widget/chat.css`: plain JavaScript and CSS, no libraries, added with one script tag.
  Launcher button, header with Demo label, bubbles, typing dots, quick-reply buttons, light and dark theme,
  full-screen on phones. All classes start with `sc-` so the school website's styles don't clash.
- Opening flow: greeting, campus choice, group choice (exploring admissions / current parent or student /
  business or vendor), then the group's menu. Vendor choice asks the bot (which answers from contacts.md).
- `session_id`, campus, group and the visible conversation are kept in sessionStorage (a page reload keeps the chat).
- Backend: `/widget/*` files, `/demo` test page, `/config` (school name, campuses, menus from `kb/school.json`, demo flag).
  The group is sent with each message so the bot knows who it is talking to.

**Tested**
- Headless Chromium (Playwright) with the FakeLLM: opening flow, a typed question and reply, Demo label,
  reload keeps the chat, no horizontal scroll at 400px (open and closed), dark theme colours, vendor choice.
  Screenshots in `docs/screenshots/`.
- pytest: `/config`, `/demo` and widget files served.

**What failed and how it was fixed**
- The header was cramped on desktop (title wrapped). "Restart" became an icon button with an accessible label.

**Still weak**
- Bot replies are shown as plain text with simple lists and bold; links and emails are not clickable.
- Only tested in Chromium; not yet in Safari or Firefox, or on a real phone.
- The campus list only shows campuses that have a kb/ folder (now just Campus A).
