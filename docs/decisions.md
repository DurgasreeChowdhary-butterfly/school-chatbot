# Decision log
| Date | Decision | Who decided | Notes |
|---|---|---|---|
| 18 Oct 2026 | Scope signed off (English, web chat, 3 priorities) | [boss name] | |
| 18 Oct 2026 | Pilot campus | [name] | |
| 18 Oct 2026 | Hosting | [choice] | |
| 18 Oct 2026 | Stack: Python + FastAPI + SQLite + JS widget + Claude API | [you] | Proposed |
| 18 Oct 2026 | School on leave: build with dummy content in kb/pilot-campus, swap real files later. ERP skipped for now | [you] | Replace dummy files and re-run docs/test-questions.csv |
| 21 Oct 2026 | Project setup: Python 3.12 in .venv, FastAPI app in backend/app/main.py, GET /health | [you] | DEMO_MODE read from .env (defaults to true) |
| 21 Oct 2026 | AI provider for development: Google Gemini free tier (google-genai SDK, generate_content), dummy data only | [you] | Real parent or child data must NOT go through the free tier. Suggested model: gemini-3.8-flash |
| 21 Oct 2026 | Swappable provider layer in backend/app/llm/ (neutral interface, LLM_PROVIDER in .env) | [you] | Anthropic Claude stub ready. Only provider files import an SDK |
| 21 Oct 2026 | Chat memory: last 12 messages per session, in memory only | [you] | Lost on server restart; fine for the pilot |
| 21 Oct 2026 | Model for development: gemini-3.5-flash-lite | Claude (agent) | gemini-3.8-flash timed out on every call; gemini-3.6-flash free tier is only 20 requests/day. Revisit with a paid tier |
| 21 Oct 2026 | docs/school-chatbot-demo.html is the design reference | Claude (agent) | The brief named docs/demo-reference.html, which does not exist |
| 21 Oct 2026 | Automated tests use a FakeLLM; the live model is used only for the answer-quality test | Claude (agent) | Tests are free, fast and repeatable |
| 21 Oct 2026 | Chat memory raised from 12 to 20 messages (HISTORY_LIMIT) | Claude (agent) | An enquiry takes about 5 turns; 12 messages could drop the first details before confirmation |
| 21 Oct 2026 | Enquiry saving is two steps: submit_enquiry (check + summary) then confirm_enquiry (save) | Claude (agent) | The backend refuses to save until the visitor has replied to the summary, so confirmation does not depend on the AI behaving |
| 21 Oct 2026 | Routing, classes and deadlines live in kb/<campus>/routing.json (mirrors escalation.md and contacts.md) | Claude (agent) | Code reads it; nothing school-specific is hardcoded. Role emails not in contacts.md are example.com placeholders |
| 21 Oct 2026 | Working days = Monday to Friday; holidays not counted yet | Claude (agent) | Simple and conservative. Add holidays from calendar.md later if needed |
| 21 Oct 2026 | Notifications: outbox table + log always; email only if SMTP_HOST/USER/PASSWORD are set | Claude (agent) | No real email is sent during the demo |
| 21 Oct 2026 | Ticket status needs reference + registered mobile; wrong number and unknown ticket get the same reply; 5 failed lookups per session locks lookups | Claude (agent) | Never reveal a ticket to a wrong number |
| 21 Oct 2026 | Urgent (safety) tickets notify first contact, backup and front office immediately | Claude (agent) | CLAUDE.md: safety goes straight to a human |
| 21 Oct 2026 | Tickets are created without a separate confirmation step (unlike enquiries) | Claude (agent) | The parent explicitly asks to log it; keeps urgent cases fast |
| 21 Oct 2026 | Staff page: one shared ADMIN_PASSWORD, in-memory login tokens (8 h), 5 failed logins per IP per 15 min | Claude (agent) | Simple for the pilot; per-person accounts later if needed |
| 21 Oct 2026 | Consent: request_consent tool + "I agree" card in the chat window; backend refuses to store enquiries, tickets or callbacks without it; consent time saved on each record | Claude (agent) | Ticket status lookup needs no consent (nothing is stored). Privacy notice text is in kb/<campus>/privacy_notice.md (dummy) |
| 21 Oct 2026 | Rate limits: 12 chat messages per minute per session, 40 per IP (settable in .env) | Claude (agent) | In memory; uses the direct client IP (see weaknesses if behind a proxy) |
| 21 Oct 2026 | Session ids must be 16-100 characters (letters, digits, - and _) | Claude (agent) | Makes another person's chat session impossible to guess |
| 21 Oct 2026 | Phone numbers are masked in every log line by a logging filter; message text is never logged | Claude (agent) | CLAUDE.md privacy rules |
| 21 Oct 2026 | CORS: only websites in ALLOWED_ORIGINS; empty = same server only | Claude (agent) | Add the school website before embedding |
| 22 Oct 2026 | Temperature is a setting (LLM_TEMPERATURE), left at the model default | Claude (agent) | Google's docs: "For all Gemini 3 models, we strongly recommend keeping the temperature parameter at its default value of 1.0"; lower values "may lead to unexpected behavior, such as looping". Gemini 3.6+ ignores it. Measured in docs/consistency-report.md |
| 22 Oct 2026 | Answer-quality runs are checked automatically (docs/test-checks.json, scripts/grade_answers.py) | Claude (agent) | Needed to compare runs and models. Checks match the dummy facts; update them with the real content. A person still reads answers now and then |
| 22 Oct 2026 | Chat sessions (history, consent, pending enquiry, failed lookups) stored in SQLite table chat_sessions | Claude (agent) | Survives restarts and works with more than one server process on the same database file. Deleted after 2 hours idle |
| 22 Oct 2026 | Email: outbox row first (pending), then sent in a background thread, urgent first; failed rows retried after 1, 5, 15, 60 min (5 tries), staff Resend button | Claude (agent) | The chat reply never waits for the mail server. Rows are claimed before sending so two server processes do not send twice |
| 22 Oct 2026 | TEST_MODE=true by default: every email goes to TEST_RECIPIENT; placeholder domains (example.com/.org/.net, .example, .test, .invalid, localhost) are never emailed | Claude (agent) | Safe while kb/ holds dummy addresses. Turn off only when the school approves real sending |
| 22 Oct 2026 | Working days from config/working_days.json: Monday to Saturday with only the 1st and 3rd Saturdays, plus the holidays in calendar.md (replaces "Monday to Friday, no holidays") | Claude (agent) | calendar.md says first and third Saturdays are working. Summer vacation end (31 May 2027) is assumed; calendar.md gives only the start. A test checks the holidays agree with calendar.md |
| 22 Oct 2026 | scripts/check_kb.py is the go-live gate for content: required files and headings, routing vs escalation.md, holidays vs calendar.md, and no DUMMY / example.com / +91 00000 when DEMO_MODE=false | Claude (agent) | Required headings are listed in the script (structure only, no school facts). kb/<campus>/README.md is also sent to the AI, so it must be rewritten or deleted too |
| 22 Oct 2026 | Deploy package: Docker (python:3.12-slim, non-root, one worker) + Caddy 2.8.4 for automatic HTTPS; kb/ and config/ mounted read-only; database in a named volume; nightly scripts/backup_db.py | Claude (agent) | Not deployed. Hosting still to be chosen by the school. One worker because staff logins and rate limits are in memory |
