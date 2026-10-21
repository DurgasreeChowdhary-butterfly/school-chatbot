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
