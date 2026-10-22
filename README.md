# School Chatbot
Website chat assistant for school enquiries and parent support. See CLAUDE.md for context and docs/ for scope,
decisions (docs/decisions.md), progress and known weaknesses (docs/progress.md) and risks.

Folders: backend/ (server), widget/ (chat window for the website), kb/ (approved school content, one folder per campus),
docs/, scripts/ (live test helpers), tests/ (automated tests).

> All content in kb/ is DUMMY data for a fictional school. Never send real parent or child data through the Gemini free tier.

## Set up (Windows PowerShell, once)
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m playwright install chromium      # only needed for the browser tests
Copy-Item .env.example .env                # then fill in GEMINI_API_KEY, MODEL_NAME and ADMIN_PASSWORD
```

## Run
```powershell
.\.venv\Scripts\Activate.ps1
uvicorn backend.app.main:app --reload
```
| Address | What it is |
|---|---|
| http://127.0.0.1:8000/demo | Test page with the chat window |
| http://127.0.0.1:8000/staff | Staff page (password = `ADMIN_PASSWORD` in .env) |
| http://127.0.0.1:8000/health | Health check |
| http://127.0.0.1:8000/docs | Automatic API documentation |

Ask a question from PowerShell (session ids must be 16 to 100 letters, digits, `-` or `_`):
```powershell
$body = @{ session_id = "test-session-0001"; message = "What is the minimum age for Grade 1?" } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/chat -Method Post -ContentType "application/json" -Body $body
```

## Deploy
See `docs/deploy.md`: Docker (`Dockerfile`, `docker-compose.yml`) with Caddy for automatic HTTPS, environment
variables, backups (`scripts/backup_db.py`), adding the chat to the website, and health checks.

## Chat window on a website
Put one line before `</body>` on the school website:
```html
<script src="https://YOUR-SERVER/widget/chat.js" defer></script>
```
Optional attributes: `data-campus="pilot-campus"` (skip the campus question), `data-open="true"`, `data-theme="light"` or `"dark"`.
Add the website's address to `ALLOWED_ORIGINS` in .env (for example `https://www.school.example`), or the browser will block the chat.
School name, campuses and menu buttons come from `kb/school.json`.

## What the bot can do
- Answer from the approved content in `kb/<campus>/*.md` only (rules in `backend/app/prompts.py`).
- Admission enquiries and visit requests: privacy notice and "I agree" first, then details, a summary, and saving only
  after the visitor says yes. Duplicates by mobile number get a note instead of a new enquiry.
- Concerns: tickets routed by category, urgent handling for safety, status lookup with reference + registered mobile.
- "Talk to a person": callback requests for the front office.
- Notifications go to the `outbox` table and the server log, and are emailed when `SMTP_HOST` is set in .env.
  Urgent (safety) emails go first; failed emails are retried every minute or so (up to 5 tries) and can be resent
  from the staff page. `TEST_MODE=true` (the default) sends every email to `TEST_RECIPIENT` only, and nothing is
  ever sent to an example.com address.
- A reminder job (every 15 minutes) reminds and escalates enquiries and tickets after the working-day deadlines in
  `kb/<campus>/routing.json`. Working days (Monday to Saturday, which Saturdays, school holidays) are in
  `config/working_days.json`.

## Test
- **Automated tests** (FakeLLM, no API calls, free, about 15 seconds): `python -m pytest`
  The browser tests save screenshots to `docs/screenshots/`.
- **Answer-quality test** (live model, uses your free-tier quota). Start the server, then:
  ```powershell
  python scripts/run_test_questions.py --out docs/test-runs/latest.json
  python scripts/run_test_questions.py --file docs/test-questions-extra.csv --out docs/test-runs/extra.json
  python scripts/show_results.py docs/test-runs/latest.json
  ```
  Judge each answer against the "expected" column and update `docs/test-report.md`.
- **A multi-turn conversation** with the live model (taps "I agree" for you):
  `python scripts/live_conversation.py "I want to book a visit" "Sample Parent, Sample Kid, Grade 3" "9876543210"`

## Switch the AI provider
All AI calls go through `backend/app/llm/`. Only files in that folder may import a provider SDK.
- `LLM_PROVIDER=gemini` uses `gemini_provider.py` (needs `GEMINI_API_KEY` and `MODEL_NAME`).
- `LLM_PROVIDER=fake` uses the scripted FakeLLM (for tests and offline demos).
- To use Claude: fill in `generate()` in `llm/anthropic_provider.py` (convert the neutral `Message`, `ToolSpec` and
  `ToolCall` to the Anthropic Messages API and back), add `anthropic` to requirements.txt, then set
  `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY` and `MODEL_NAME`. Run `python -m pytest` and the answer-quality test.
- Before any real parent or child data is used, move to a paid tier or provider whose terms fit the school's privacy rules.

## Replace the dummy content with the school's real content
**Step 0, the school's documents (PDF, Word, Excel, photos):** put them in `incoming/` (not stored in Git) and run
`python scripts/ingest_docs.py`. It writes drafts in the same structure as kb/ to `drafts/pilot-campus/`, marks
anything unclear, missing or conflicting with "NEEDS REVIEW: ...", writes "Not provided" where the documents say
nothing (it never makes up facts and does not use the AI), and lists questions for the school in
`docs/content-review.md`. Photos are read with the OCR built into Windows 10/11. Fix every mark, then
`python scripts/approve_kb.py` copies the drafts into kb/ (it refuses while any mark is left), then carry on below.

1. For each campus, replace the files in `kb/<campus>/` with the school-approved versions. Keep the file names and headings.
   `privacy_notice.md` must be the school's approved notice.
2. Update `kb/<campus>/routing.json` to match `escalation.md` and `contacts.md` (real role emails, classes, deadlines).
   The test `test_routing_file_matches_escalation_md` checks the categories agree.
3. Update the holidays and working Saturdays in `config/working_days.json` to match the real `calendar.md`.
   The test `test_config_holidays_match_calendar_md` checks they agree.
4. Update `kb/school.json` (school name, campuses, menu buttons). A new campus needs its own `kb/<campus-id>/` folder.
5. Run the content checker: `python scripts/check_kb.py --live`. It lists missing files or headings, routing or
   holidays that disagree with escalation.md / calendar.md, and any leftover DUMMY text, example.com address or
   "+91 00000" number. (You can check a folder of new files first: `python scripts/check_kb.py --live --kb C:/path/to/new-kb`.)
   Set `DEMO_MODE=false` in .env only when it says "All checks passed" and everything in kb/ is approved.
6. Restart the server, run `python -m pytest`, then the answer-quality test, and update `docs/test-report.md`.
