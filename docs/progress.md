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

## Stage C: Enquiry capture (21 Oct 2026)

**Built**
- Tools `submit_enquiry` and `confirm_enquiry` (`enquiry_tools.py`), offered through the provider layer.
  The class list in the tool comes from `kb/pilot-campus/routing.json`.
- Backend validation (`validation.py`): names (letters only), class from the list, 10-digit Indian mobile
  (accepts +91, 0, spaces, dashes), optional previous school/reason, visit preference.
- Confirmation is enforced by the backend: `submit_enquiry` only checks and stores a draft; `confirm_enquiry`
  refuses if the visitor has not sent a new message since the summary was made.
- SQLite storage (`db.py`, file `data/chatbot.db`) with tables enquiries, tickets, callbacks, outbox.
  References look like E-1001.
- Duplicate check by mobile number per campus: a note is added to the existing enquiry instead.
- Counsellor from `routing.json` (email can be overridden by `COUNSELLOR_EMAIL_PILOT` in .env).
- Notifications (`notify.py`) go to the outbox table and the log (subject only). Real email only if SMTP settings exist.
- Reminder job (`jobs.py`, every 15 minutes): enquiry still "New" after 1 working day -> reminder to the counsellor;
  after 2 working days -> escalation to the front office. Working days are Monday to Friday.
- Chat memory raised from 12 to 20 messages so a full enquiry conversation fits.

**Tested**
- pytest (FakeLLM): mobile and name validation, saved after confirmation, tools offered with the class list,
  no confirm in the same turn, no confirm without submit, invalid and missing details, duplicate adds a note,
  counsellor email override, working days over a weekend, reminder then escalation (not repeated), no reminder once contacted.
- Live with Gemini (one 5-message conversation, throwaway database): the bot asked for details in groups,
  showed a summary, waited for "yes", saved E-1001 and the outbox got the counsellor notification. Mobile masked in the log.

**What failed and how it was fixed**
- The history test assumed 12 messages; it now follows the setting.

**Still weak**
- School holidays are not counted as non-working days (only weekends).
- Sessions are in memory: a pending (unconfirmed) enquiry is lost if the server restarts.
- The duplicate check uses the mobile number only; two families sharing a phone would be merged into one enquiry with a note.

## Stage D: Concern tickets (21 Oct 2026)

**Built**
- Tools in `ticket_tools.py`: `create_ticket` (category, description, parent name, mobile), `get_ticket_status`
  (ticket reference + registered mobile) and `request_callback` (name, mobile, optional reason).
- Categories, first contact, backup and the urgent flag come from `kb/pilot-campus/routing.json`.
- Safety, health and bullying tickets are urgent: the principal, vice principal and front office are notified at once,
  and the bot is told to send the person to the front office phone immediately.
- Status lookup: a wrong mobile and a missing ticket get the exact same "no match" answer, so nothing leaks.
  After 5 failed lookups in one chat, lookups are refused for that session.
- Statuses: Received, In progress, Resolved. The reminder job reminds the first contact if a ticket is still
  "Received" after 1 working day, and escalates to the backup if not resolved after 3 working days.
- Rules in `prompts.py` for concerns, urgent cases, status lookups and callbacks.

**Tested**
- pytest (FakeLLM): routing.json matches escalation.md, routing by category, validation, urgent safety ticket
  notifies 3 roles, lookup with right mobile (and after a status change), wrong-number lookup reveals nothing,
  lockout after 5 failures (other sessions unaffected), callback saved and routed, invalid callback mobile,
  acknowledge reminder then escalation to backup, no reminder once in progress, resolved tickets left alone. 43 tests pass.
- Live with Gemini (two conversations): diary concern -> T-1001 to the class teacher; status with a wrong number -> no match;
  right number -> "Received"; bullying -> contacts first, then urgent T-1002 with three notifications.

**What failed and how it was fixed**
- Nothing failed in this stage. The shared test helper moved to `tests/conftest.py`.

**Still weak**
- Ticket status changes do not notify the parent (no SMS/WhatsApp in scope).
- The lockout is per chat session; someone could start new sessions to keep guessing (Stage F adds rate limits).
- The bot decides the category; a wrong choice routes to the wrong person (staff can see it on the staff page).

## Stage E: Staff page (21 Oct 2026)

**Built**
- `/staff` (`staff.py`, pages in `backend/app/staff_pages/`): login with `ADMIN_PASSWORD` from .env.
  Login is switched off (with a clear message) if the password is empty.
- Login protection: 5 wrong attempts per IP in 15 minutes blocks further tries; constant-time password check;
  login cookie is random, HttpOnly, SameSite=Strict, limited to /staff, expires after 8 hours.
- Shows enquiries, tickets (urgent and escalated marked), callback requests and the outbox (click a subject to read it).
- Staff change statuses from a drop-down (enquiries: New, Contacted, Visit booked, Closed; tickets: Received, In progress,
  Resolved; callbacks: New, Called back). Changes need a header only the staff page sends (blocks cross-site forms).
- CSV export for each table; cells that start like a spreadsheet formula are made safe.
- "Run reminders now" button. Demo label and banner while DEMO_MODE=true. Light and dark theme.

**Tested**
- pytest: page needs login, wrong password, login and data, rate limit (right password refused after 5 failures),
  login off without password, logout, status changes (valid, invalid, missing), header required, CSV export and formula safety,
  reminders button. 54 tests pass.
- Browser: wrong then right password, sample rows shown, status changed in the drop-down and saved, no horizontal scroll
  at desktop and 400px. Screenshot `docs/screenshots/5-staff-view.png`.

**What failed and how it was fixed**
- `python-multipart` was missing for the login form; added to requirements.txt.

**Still weak**
- One shared staff password; no per-person accounts or audit of who changed what.
- Logins are kept in memory: everyone is logged out when the server restarts.
- The login rate limit is per IP; staff behind one office network share the limit.

## Stage F: Hardening (21 Oct 2026)

**Built**
- Privacy notice (`kb/pilot-campus/privacy_notice.md`, dummy) and consent: the AI calls `request_consent` before asking
  for details; the chat window shows the notice with "I agree" / "No thanks"; `POST /consent` records it.
  The backend refuses to store enquiries, tickets or callbacks without consent, and saves the consent time on each record.
- Rate limits on `/chat` and `/consent`: 12 per minute per session, 40 per minute per IP (settable in .env).
- Input limits: messages 1 to 1000 characters (friendly replies for empty or too long), session ids 16 to 100 safe
  characters, campus ids checked. Bad requests never return a stack trace.
- Phone numbers masked in every log line (logging filter); message text is never logged.
- CORS: only websites listed in `ALLOWED_ORIGINS`.
- Fix found in the live run: if the AI re-checks the same enquiry details when the person says "yes", the confirmation
  now works (changed details still need a new "yes").
- Rules: consent only when about to collect details; information first for concerns and "talk to a person";
  never fill in missing details; invalid numbers rejected anywhere; "next" dates worked out from today.
- README: run, test, switch provider, replace dummy content.

**Tested**
- pytest (79 tests, about 15 seconds, no API calls): consent shown, nothing saved without consent, consent unlocks and is
  recorded, "No thanks" withdraws, lookups need no consent, empty and very long messages, bad session/campus ids,
  per-session and per-IP rate limits, phone masking (text, log handler, full save flow), CORS allow/deny,
  prompt injection (rules unchanged by user text, tricked model can't read another ticket or skip confirmation,
  nasty tool arguments rejected), provider failing mid-tool and provider not creatable, resubmit-then-confirm.
- Browser: consent card on a phone (screenshot 6), "I agree" calls `/consent` and continues the chat.
- Live: all 40 questions + 10 extra cases, then a rerun of the affected and must-pass questions, and a full
  enquiry conversation through consent (saved E-1001). See `docs/test-report.md`.

**What failed and how it was fixed**
- First final live run: the bot asked for consent instead of answering (25, 39, 108), accepted an invalid number (20),
  didn't work out the next PTM (21), asked for details before consent (31, 109), made up a visit time, and an enquiry
  could not be confirmed because the AI re-submitted on "yes". Fixed with clearer rules and the backend fix above;
  rerun passed.
- Two older tests needed updating (new reply fields; a test that now hits the session rate limit).

## Reliability round (22 Oct 2026)

### 1. Consistency
**Built**
- `LLM_TEMPERATURE` setting (empty = model default). Google's docs strongly recommend the default (1.0) for Gemini 3
  models and say lower values may cause looping; Gemini 3.6+ ignores it. Kept at the default after measuring both.
- Automatic answer checks: `docs/test-checks.json` + `scripts/grade_answers.py` (pass / fail with reasons / error);
  `run_test_questions.py` prints them at the end; `scripts/consistency_report.py` makes the per-question table.
- Q25 fix (rule): say what the person can get themselves (a duplicate receipt at the accounts office) first.
- Q15 fix (rule + code): copy contact details exactly; garbled emails repaired; a made-up email or phone number gets one
  corrected reply, otherwise it is replaced by the front office number.
- The Gemini provider now says "(daily quota used up)" in its error, so scripts can tell quota from other failures.

**Tested**
- Live, 40 questions x 3 runs at the default temperature: 40, 39, 40 pass (Q15 flipped: garbled email).
  After the fixes: 12 must-pass and flipped questions 12/12, Q15 3 more times 3/3.
  40 x 3 at temperature 0.2 (with the fixes): 40, 40, 40. No looping. Details in `docs/consistency-report.md`.
- All 240 answers were also read by hand; the automatic checks agreed.
- pytest: 6 new tests for the email repair and contact check.

**What failed and how it was fixed**
- The first automatic Q15 check was too strict (failed "no teaching positions listed"); loosened.
- First version of the contact check treated a made-up address as known after the retry, because it was quoted in the
  check message; the known contacts are now taken before the retry (a test caught this).
- Scripted file edits on Windows switched several files to CRLF line endings; restored to LF in a separate commit.

**Still weak**
- 3 runs of 40 single questions is small; rare slips (1 in 50) may not show. Multi-turn flows were not repeated here.
- Answers vary in wording from run to run at either temperature; the facts did not.


### 2. Model comparison
**Built**
- `scripts/compare_models.py MODEL [MODEL ...]`: runs the 40 questions for each model in-process (no server needed,
  throwaway database) and prints a table of pass / fail / error counts from the automatic checks.
- Each model first gets one tiny request; a model whose daily quota is used up, or that does not answer, is skipped.
  A model that runs out part-way is stopped after 3 failed replies in a row and marked "stopped".
- Answers are saved to `docs/test-runs/compare-<model>.json`. Options: `--only 5 6 25`, `--gap 8`.

**Tested**
- Dry run with `LLM_PROVIDER=fake` (two made-up model names, two questions): table printed, no API calls.
- Live (22 Oct 2026, default temperature, after the item 1 fixes):

  | Model | Pass (of 40) | Fail | Error | Run |
  |---|---|---|---|---|
  | gemini-3.5-flash-lite | 40 | 0 | 0 | complete |
  | gemini-3.1-flash-lite | 39 | 0 | 1 | complete |

  The 3.1 "error" (Q10) was Google's servers staying busy (503) through all retries, not a wrong answer. By hand, 3.1's
  answers were also fine, a little wordier, and once (Q17) offered the front office without giving its number.
  gemini-3.6-flash was not run: its free tier allows only 20 requests a day, fewer than one full test.

**What failed and how it was fixed**
- First live run: gemini-3.5-flash-lite was skipped because its one test request hit a passing timeout (504), and
  a busy-server failure counted as an error. The test request is now tried 3 times (a used-up quota is still not
  retried), and fallback replies are retried after 15 and 30 seconds, like `run_test_questions.py`.

### 3. Persistence
**Built**
- Chat sessions are stored in SQLite (new table `chat_sessions`): the visible conversation, consent time, the enquiry
  waiting for "yes", the turn counter and failed ticket lookups. Each request loads its session and saves it afterwards
  (also when the AI fails), so a restart in the middle of a conversation loses nothing.
- Sessions idle for 2 hours are deleted from the database, as before (they can contain names and mobile numbers).

**Tested**
- pytest (6 new tests, 85 in total): the app is stopped and started again mid-conversation, with nothing kept in memory.
  The conversation continues, consent is still given, a pending enquiry can be confirmed with "yes" after the restart,
  the summary and "yes" still need separate turns, the 5-failed-lookups limit is not reset, idle sessions are deleted.

**Still weak**
- Staff logins and rate limits are still in memory (a restart logs staff out and resets the limits).
- Two messages from the same chat at exactly the same moment: the later save wins (the chat window sends one at a time).

### 4. Real email
**Built**
- `notify.py`: every notification is written to the outbox, then emailed through the SMTP settings in .env
  (`SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY` = starttls / ssl / none, optional `SMTP_USER` and `SMTP_PASSWORD`, `SMTP_FROM`).
- Outbox statuses: pending, sent (with the address used and the time), failed (with the error), blocked (not sent on
  purpose, with the reason), logged (email not set up).
- `TEST_MODE=true` (default): every email goes to `TEST_RECIPIENT`, with "[TEST, for <role> <address>]" in the subject.
  Placeholder addresses such as example.com are never emailed, even with TEST_MODE off.
- Urgent emails (safety tickets and their reminders) are sent before anything else waiting in the outbox.
- Failed emails are retried by the background job (checks every minute; waits 1, 5, 15, 60 minutes; 5 tries in all).
  The staff page shows tries and errors and has a Resend button on each row.
- Sending runs in a background thread so the chat reply never waits for the mail server. Older databases get the new
  outbox columns automatically.

**Tested**
- pytest with a fake SMTP server (a real local socket server, 14 new tests, 99 in total): redirect to the test recipient,
  never to example.com (test mode on and off), no test recipient means nothing sent, real address with test mode off,
  temporary failure then retry, retries stop after 5, server down, staff resend (login and header needed),
  urgent safety emails sent before older routine ones, no SMTP means logged only, old database upgraded.
- Not tested against a real mail provider (no SMTP account was used).

**Still weak**
- Emails waiting in the outbox are only retried while the server is running.
- A real provider (Gmail, Microsoft 365, the school's own) may need an app password and limits the number of emails per day.

### 5. Working days
**Built**
- `config/working_days.json`: `week` ("Monday to Saturday" or "Monday to Friday"), `working_saturdays` ([1, 3] from
  calendar.md, or "all"), and the holidays from `kb/pilot-campus/calendar.md` (dates as YYYY-MM-DD).
- `backend/app/workdays.py` reads and checks it (clear messages for mistakes; the server will not start with a broken
  file). Reminder and escalation deadlines now skip Sundays, non-working Saturdays and holidays.

**Tested**
- pytest (10 new tests, 109 in total): 1st/3rd Saturdays, holidays (Diwali, one-day Christmas), the two week settings,
  four kinds of mistakes in the file, holidays agree with calendar.md, an enquiry reminder that waits for Dussehra to end,
  a ticket escalation across a working Saturday and Diwali.
- Two older reminder tests used 19-22 Oct 2026, which are now Dussehra holidays; they were moved one week later
  (same checks).

**Still weak**
- The summer vacation end (31 May 2027) is assumed: calendar.md only says "from 1 May 2027".
- One calendar for all campuses; a second campus with different holidays would need its own file.

### 6. Content checker
**Built**
- `scripts/check_kb.py` prints a checklist and exits with 1 if anything needs fixing:
  `school.json` and a folder per campus; the 14 required files with their headings (and key lines such as
  "Office hours" and "Holidays:"); `routing.json` keys, roles, deadlines and categories agree with `escalation.md`;
  `config/working_days.json` is valid and its holidays agree with `calendar.md`.
- With `DEMO_MODE=false` (or `--live`) it fails every file that still has the word DUMMY, an example.com address or a
  "+91 00000" phone number. `--kb` checks a folder of new files before they are copied into kb/.

**Tested**
- pytest (9 new tests, 118 in total) on a copy of kb/: dummy content passes in demo mode and fails with demo mode off;
  cleaned content passes; each kind of leftover is caught; missing file and heading; routing that disagrees with
  escalation.md; a holiday date that disagrees with calendar.md.
- Run on the real repo: all checks pass in demo mode; `--live` lists 18 files with dummy content (expected today).

**Still weak**
- It checks structure and leftovers, not whether the facts are right. The school must still approve every file, and
  `docs/test-checks.json` must be updated with the real facts before the answer-quality test means anything.

### 7. Deploy package
**Built**
- `Dockerfile` (Python 3.12 slim, runs as a normal user, one worker, Docker health check on `/health`,
  proxy headers so rate limits see the visitor's IP behind Caddy) and `.dockerignore` (never copies `.env`, data or tests).
- `docker-compose.yml`: the chatbot (not open to the internet) and Caddy 2.8.4 (ports 80/443, automatic HTTPS from
  `CHATBOT_DOMAIN`, config in `deploy/Caddyfile`). The database is in a named volume; `kb/` and `config/` are mounted
  read-only so content changes need only a restart.
- `/health` now also checks the database can be read (503 and `"database": "error"` if not).
- `scripts/backup_db.py`: safe copy while running (SQLite backup), integrity check, keeps the newest 30.
- `docs/deploy.md`: step by step for a beginner: what you need, .env table, HTTPS, start, health checks, adding the
  script tag and ALLOWED_ORIGINS, nightly backups, off-server copies, restore, updates, go-live checklist, troubleshooting.

**Tested**
- pytest (2 new tests, 120 in total): broken database gives 503; backup copy is readable and old copies are pruned.
- `docker compose config` accepts the compose file (and refuses to start without `CHATBOT_DOMAIN`).
- **Not tested:** building and running the image. Docker is installed but Docker Desktop was not running, and starting
  it was left to you. Run `docker compose up -d --build` once on a test machine before the real server.

### 8. Real-site embed test
**Built**
- `docs/embed-test.html`: a pretend school website (with deliberately clashing styles) that adds the chat with one
  script tag pointing at the chatbot server on a different address. How to try it by hand is in the file.
- `tests/test_embed_browser.py` (headless Google Chrome, Chromium if Chrome is missing): starts the chatbot allowing
  one website origin, and serves the page from two website origins.

**Tested**
- Allowed website: the script comes from the other origin; campuses load from `/config`; the opening flow, a question
  and the reply work; Demo label shown; no console errors; no sideways scroll at phone width. Screenshot 7.
- Blocked website (not in ALLOWED_ORIGINS): the chat window opens but the message gets the friendly "I'm having
  trouble" reply, and Chrome reports the CORS block. Screenshot 8.
- Server side: the CORS preflight is answered only for the allowed origin.

**What failed and how it was fixed**
- The school site's `button, input { text-transform: uppercase }` changed the chat window's input. The widget CSS now
  resets inherited text styles on its root and its buttons and inputs.

**Still weak**
- Only Chrome on Windows was tested; not Safari, Firefox or a real phone.
- On a blocked site the visitor only sees "I'm having trouble"; the reason is visible only in the browser console.

## Real-content round (22 Oct 2026)

### 1. Document ingestion
**Built**
- `scripts/ingest_docs.py`: reads everything in `incoming/` (in .gitignore): PDF (text), Word (.docx, with tables),
  Excel (.xlsx), .txt/.md/.csv, and photos with the OCR built into Windows (`scripts/ocr_windows.ps1`, free, offline).
  Old .doc/.xls, scanned PDFs and unreadable files are listed as "needs manual typing".
- It sorts each line into the kb file and section it belongs to (same names and headings as kb/pilot-campus), keeps a
  `<!-- source: file, page -->` note, and marks "NEEDS REVIEW: <reason>" for: misread text, tentative wording,
  dates without a year, open-ended dates, relative dates, possible personal data (Aadhaar-like or personal mobile
  numbers), and the same fact with different values (fees per class and type, holiday dates, role phones/emails).
- Empty sections and files say "Not provided". The required lines (Office hours, Front office phone, Admission
  counsellor, Holidays:) are always present; the Holidays line is built only from dates in the documents.
- `docs/content-review.md`: documents read, files needing manual typing, numbered questions for the school
  (conflicts, missing items per file, things to confirm), a list for the reviewer (misread text, personal data),
  and unsorted lines. It is rule-based: it does not use the AI, so it cannot invent facts.
- `scripts/approve_kb.py`: copies drafts to kb/ only when no NEEDS REVIEW is left and the headings are there
  (all files, or `--partial`), removes the draft notes and source comments, backs up the replaced files to
  `drafts/_replaced/`, then runs the content checker.

**Tested**
- Three fake messy documents (`tests/messy_docs.py`): a PDF fee circular (wrapped sentence, tentative late fee),
  a Word calendar (holiday table with From/To columns, open-ended vacation, "to be announced"), and a "photo" text file
  (OCR mistakes like SCH00L and n0t, "next Saturday", a personal mobile number, and an annual fee of Rs 27,000 that
  conflicts with Rs 26,000 in the circular). The sample report is `docs/content-review.md`.
- pytest (12 new tests, 140 in total): every file drafted with its headings; the conflict is marked on both lines and
  asked; each kind of unclear line is marked; missing topics say Not provided; the Holidays line; no number appears in
  the drafts that is not in the documents; unreadable files are listed; a real photo read with Windows OCR;
  approve refuses with marks left, copies clean files and backs up, `--partial`, and a missing heading.

**What failed and how it was fixed**
- "Admission counsellor: ..." was sorted into admissions.md, so contacts.md said it was missing; lines the chatbot
  needs in a file now go to that file first.
- "holi" matched inside "holidays"; one-day holidays showed "25 to 25 December"; "from 1 May" lost its "from". Fixed.
- The draft note contains the words NEEDS REVIEW, so approve counted it; the note is now skipped (it is removed on copy).

**Still weak**
- Keyword sorting is rough: some lines will land in the wrong file and must be moved by hand. The drafts are raw
  lines, not polished text: a person writes the final wording.
- Conflict checks cover fees, holiday dates and role contacts only; other conflicts (timings, ages) need a careful read.
- Tables in PDFs lose their column headings; such rows are kept as they are and need checking.

### 2. Test generation
**Built**
- `scripts/generate_checks.py`: reads the knowledge files and writes `docs/test-checks.draft.json` (question, group,
  expected, source file and the automatic checks, in the format of test-checks.json) and
  `docs/test-questions.draft.csv` (format of test-questions.csv). Questions come from templates filled with facts in
  the files (ages, fees per class, payment, receipts, sibling concession, board, affiliation, timings, contacts,
  holidays, exams, hiring, transport, PTM, who handles each concern), plus 16 fixed cases (discount and admission
  promises, safety and health, privacy and injection, marks, ticket status, invalid number, visit booking with
  consent, out of scope, comparison, a topic not in the content, greeting). No AI is used.
- Topics where no facts were found are listed; questions that need a person's attention carry a `review_note`.
- Today it proposes 49 questions from the dummy content (3 with a review note). The drafts are committed as a sample.

**Tested**
- On the 38 questions that match the current test, the generated checks were applied to all 228 live answers from
  item 1: they agreed with the hand judgement on 227; the one failure is the real mistake (garbled email, Q15).
- pytest (4 new tests, 144 in total): about 40 questions with valid patterns and the required kinds of cases; the
  generated checks pass the 120 hand-checked answers at temperature 0.2; questions follow the content (a changed fee
  appears in the check); an empty folder reports the missing topics and keeps the fixed cases.

**What failed and how it was fixed**
- The 20%-discount case first failed any answer containing "guarantee" (which would fail "I cannot guarantee");
  it now only fails "is guaranteed" or an offer of 20%.

**Still weak**
- Template questions are less varied than real parents' questions. The "next PTM" check needs the exact date added by hand.

### 3. Simulated users
**Built**
- `scripts/simulate_users.py`: runs enquiry and ticket conversations with the live model against scripted users with a
  profile and a style: a normal user, misspellings, several details in one message, changing their mind, wrong formats,
  Tenglish, an invalid then a valid number, trying to skip consent, and (tickets) a wrong-number status lookup.
  The users answer what the bot asks, tap "I agree" (except when skipping consent) and stop at a reference.
- Every conversation has its own empty database; pass/fail is decided by what was saved there: names, class, mobile,
  visit time actually given, consent time, the reference told to the user, no made-up references, the notification,
  nothing saved without consent or after "don't log it", and nothing revealed to a wrong number.
- `--runs 10` (default) = 10 runs of each of the 17 scenarios, round-robin so stopping early still covers all;
  results are saved after each conversation and a new run carries on; it stops at the daily quota.

**What failed and how it was fixed**
- Pilot (1 run of each scenario, live): 17 of 17 passed the first checks, but reading the transcripts showed the model
  saved "No visit for now" for a visitor who was never asked about a visit. Fixed in code, not only in the rules:
  `validation.made_up()` makes enquiries, tickets and callbacks refuse any name, mobile, class or visit time that does
  not appear in what the person typed in this chat, and tells the model to ask for it. The simulator now checks this too.
- Tests: the shared test helper now puts the details in the visitor's message (as a real visitor would); 4 new tests
  for the check (169 in total).
- First real attempt: the new check refused "Saturday morning" when the visitor typed "satrday mornig", and the model
  looped asking for a date. Fixed: small spelling differences are accepted (1 more test). A network drop gave 1 error.
- Simulator gaps (not chatbot failures), fixed in the simulator and rerun: it did not recognise "Would you like to log
  this...?" without "me"; runs that ended in an error are now retried on the next run.

**Tested (live, 22 Oct 2026)**: pilot 17 of 17; final run 15 of 15 passed (run 1 of 15 scenarios) before the
**daily free-tier quota ran out** (stopped before ticket:skip_consent run 1). Not yet run: ticket:skip_consent and
ticket:lookup_wrong_number (both passed in the pilot), and runs 2 to 10 of every scenario (153 conversations).
Carry on after midnight Pacific time with `python scripts/simulate_users.py` (it continues where it stopped; about
170 conversations need roughly 2 to 3 days of free quota). Report: `docs/simulation-report.md`.

**Still weak**
- Only 1 run per scenario so far: rare slips will not show until the remaining runs are done.
- Scripted users follow a pattern; real parents are more varied. The checks look at what was saved, not the tone.

### 4. Security review
Full details: `docs/security-review.md`.

**Checked:** HTML/script in parent text on the staff page, SQL injection, CSRF, cookie flags, security headers, login
brute force, data leaks in the API and logs, secrets in the repository and history, CORS, package vulnerabilities.

**Fixed (each with tests):**
- Security headers on every response; strict Content-Security-Policy (inline script allowed by hash) and no-store on
  the staff pages, `/chat` and `/consent`; HSTS over HTTPS.
- Login: 50 failures from all addresses in 15 minutes block logins; passwords shorter than 12 characters switch login off.
- A cross-site form post to a staff endpoint crashed the error handler (500); error replies no longer echo the input.
- `/docs` and `/openapi.json` are off when `DEMO_MODE=false`.
- `ALLOWED_ORIGINS` ignores `*` and malformed entries (warning in the log).
- Chat session ids on plain-http sites used `Math.random`; now `crypto.getRandomValues`.

**Confirmed already safe (now with tests):** staff page escaping (real browser, 4 attack strings in every field),
parameterised SQL, the staff-page header and SameSite=Strict cookie against CSRF (also from an allowed website),
cookie flags, no names or numbers in logs, staff data needs login. No secrets in the repository or its history;
the real key is only in `.env`. `pip-audit`: no known vulnerabilities.

**Tested:** 21 new tests (18 in `test_security.py`, 3 in the browser), 169 in total, all passing.

**Still open** (see the review): one shared staff password, records never deleted (privacy notice says 12 months),
unpinned package versions, logins and limits in memory.

### 5. Docker
**Skipped:** Docker is installed but Docker Desktop was not running (checked twice on 22 Oct), so the image was not built
and docker compose was not run. To do it yourself: start Docker Desktop, then
`$env:CHATBOT_DOMAIN="http://localhost"; docker compose up -d --build` (the `http://` makes Caddy serve plain HTTP, no
certificate), then open http://localhost/health, ask a question on http://localhost/demo, and run
`curl.exe -H "X-Forwarded-For: 1.2.3.4" ...` style requests to see the limit hold.

**Tested without Docker (the part that matters for the rate limit):** `tests/test_proxy_headers.py` starts uvicorn
exactly as the image does (`--proxy-headers`, trusted proxy from `FORWARDED_ALLOW_IPS`), with 127.0.0.2 as the proxy
and 127.0.0.1 as a direct client, and uses `/consent` (rate limited like `/chat`, no AI calls):
- A client sending its own fake `X-Forwarded-For` values is still limited by its real address (4th request: 429).
- Through the proxy, the limit uses the real visitor address the proxy added, not the fake one the visitor sent first;
  another visitor behind the same proxy is not blocked.
- With the old setting `--forwarded-allow-ips "*"` a direct client **could** dodge the limit with fake headers.

**Fixed:** the Dockerfile no longer trusts every address. docker-compose.yml gives Caddy a fixed address
(172.30.0.2) on a private network and sets `FORWARDED_ALLOW_IPS` to it; the image's default trusts only 127.0.0.1.
`docker compose config` accepts the file. 3 new tests (172 in total).

### 6. Test email
**Built**
- `scripts/send_test_email.py`: sends one email through the SMTP settings in .env to `TEST_RECIPIENT`, using the same
  code as the outbox. Refuses placeholder addresses and missing settings, and explains failures in plain words: server
  name not found, cannot connect (port or firewall), wrong password (app passwords for Gmail/Microsoft 365), security
  setting not matching the port, server offers no login, sender or recipient refused, server closed the connection,
  temporary (4xx) and permanent (5xx) refusals.

**Tested**
- pytest with the fake SMTP server only (4 new tests, 176 in total): one email sent with the right subject and no
  password in it; missing or placeholder settings; a temporary refusal, no login offered and a closed port explained;
  plain advice for each kind of error. **Not run against a real mail server** (no SMTP settings in .env, as agreed).

## Known weaknesses (overall, updated 22 Oct 2026, after the real-content round)
1. **Model quality and quota.** Development uses `gemini-3.5-flash-lite` on the free tier. It is a small model and
   answers vary between runs (see docs/consistency-report.md). The bigger models failed (timeouts) or had a
   20-requests-per-day free quota. A paid tier is needed before real use, and real parent or child data must never
   go through the free tier.
2. **Rule-following is not guaranteed.** Privacy, confirmation, consent and ticket lookups are enforced in code, but
   wording (no promises, no comparisons, safety advice) relies on the model following `prompts.py`.
   Re-run the answer-quality test after every change to rules, model or content.
3. **Staff logins and rate limits are still in memory** and reset on restart. Chat sessions, consent and pending
   enquiries are now in SQLite and survive a restart.
4. **One server process.** Staff logins and rate limits do not work across several processes (the Docker set-up runs one).
5. **Reminders and email retries only run while the server is running.** The summer vacation end date is assumed.
6. **One shared staff password**, no per-person accounts or record of who changed what.
7. **Email is built but not tried with a real mail provider**; only with a fake SMTP server in the tests.
8. **Duplicate enquiries are matched by mobile only.**
9. **The AI chooses the ticket category**; a wrong choice routes to the wrong person until staff notice.
10. **Automatic answer checks look for key facts and phrases** (docs/test-checks.json); they can pass a clumsy answer
    or fail an unusual correct one, and must be updated with the real content. A person should still read answers.
11. **Browser support** was tested in headless Chromium and Chrome on Windows (desktop and phone size), not Safari/Firefox or a real phone.
12. **Not deployed.** The Docker image was never built here (Docker Desktop was not running); follow docs/deploy.md on a test machine first.
13. **Records are never deleted.** The privacy notice says 12 months; a nightly clean-up is still needed (docs/security-review.md).
14. **Package versions are not pinned**; pin them before deploying and re-run `pip-audit` monthly.
15. **Simulated users: only 1 of 10 planned runs per scenario** before the free quota ran out (all passed).
16. **Document ingestion sorts lines by keywords**; drafts need a careful human edit, and conflicts are only checked
    for fees, holiday dates and role contacts.
