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
