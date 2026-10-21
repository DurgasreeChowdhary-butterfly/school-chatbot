# School Chatbot
Website chat assistant for school enquiries and parent support. See CLAUDE.md for context and docs/ for scope, decisions and risks.

Folders: backend/ (server), widget/ (chat window for the website), kb/ (approved school content, one folder per campus), docs/, scripts/, tests/.

> All content in kb/ is DUMMY data for a fictional school. Never send real parent or child data through the Gemini free tier.

## Set up (Windows PowerShell, once)
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env   # then fill in GEMINI_API_KEY and MODEL_NAME
```

## Run
```powershell
.\.venv\Scripts\Activate.ps1
uvicorn backend.app.main:app --reload
```
- Health check: http://127.0.0.1:8000/health
- Ask a question:
  ```powershell
  $body = @{ session_id = "test-1"; message = "What is the minimum age for Grade 1?" } | ConvertTo-Json
  Invoke-RestMethod -Uri http://127.0.0.1:8000/chat -Method Post -ContentType "application/json" -Body $body
  ```

## Chat window
- Test page: http://127.0.0.1:8000/demo
- To add it to any website, put one line before `</body>`:
  `<script src="https://YOUR-SERVER/widget/chat.js" defer></script>`
  Optional: `data-campus="pilot-campus"` (skip the campus question), `data-open="true"`, `data-theme="light"` or `"dark"`.
- School name, campuses and menu buttons come from `kb/school.json`.

## Test
- Automated tests (use a FakeLLM, no API calls, free): `python -m pytest`
  The browser tests need Chromium once: `python -m playwright install chromium`. Screenshots go to docs/screenshots/.
- Answer-quality test (uses the live model and your free-tier quota): start the server, then
  ```powershell
  python scripts/run_test_questions.py --out docs/test-runs/latest.json
  python scripts/show_results.py docs/test-runs/latest.json
  ```
  Judge each answer against the "expected" column and update docs/test-report.md.
