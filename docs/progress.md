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
