# Security review (22 Oct 2026)

Scope: the staff page (`/staff`), the staff API (`/staff/api/*`, `/staff/export/*`), the public API (`/chat`,
`/consent`, `/config`, `/health`), the chat window, logs, the repository and its git history, and CORS.
Method: reading the code, trying attacks in tests (pytest and a real headless browser), scanning the git history,
and `pip-audit` on the server's packages. Every fix has a test; the test names are given below.

## Summary

| Area | Before | Now |
|---|---|---|
| Script/HTML typed by parents shown on the staff page | Already escaped | Proven in a browser with 4 attack strings in every field; CSP added as a second wall |
| SQL injection | Already safe (values are always parameters; table and column names never come from requests) | Attack tests added |
| CSRF on staff actions | Custom header + SameSite=Strict cookie | Tested, including from an allowed website; form posts no longer crash the error handler |
| Cookie flags | HttpOnly, SameSite=Strict, Path=/staff, Secure on HTTPS, 8 h | Tested |
| Security headers | None | nosniff, no framing, Referrer-Policy, Permissions-Policy, HSTS on HTTPS, strict CSP and no-store on staff pages |
| Login brute force | 5 failures per IP per 15 min | Also 50 failures from all addresses together; password must be at least 12 characters |
| Data leaks (API, logs) | Phones masked in logs; staff data needs login | Tested that names and numbers never reach the log; error replies no longer echo input; API docs off when live |
| Secrets in the repository or history | — | None found |
| CORS | Only listed websites | `*` and malformed addresses are refused with a warning; allowed websites still cannot send the staff header |
| Chat session ids | `crypto.randomUUID`, but a weak `Math.random` fallback on plain-http sites | Fallback is now `crypto.getRandomValues` (128 random bits) |

## What was checked, in detail

### 1. Script or HTML in parent-provided text (stored XSS)
Everything a parent types (names, concern text, visit time, previous school, notes) and every outbox subject and
body is shown on the staff page. The page builds its tables with an `esc()` function that escapes `& < > " '` for
every value, and the chat window escapes bot replies before adding formatting.
- **Test** `test_security_browser.py::test_parent_text_never_runs_on_the_staff_page`: puts `<script>`, an
  `<img onerror>`, an attribute break-out (`"><svg onload>`) and table-breaking markup into every field of an
  enquiry, a ticket, a callback and an outbox message, logs in with a real browser, and checks that nothing ran and the
  strings are shown as plain text (also after opening the outbox message).
- **Fix (second wall):** the staff pages now send a Content-Security-Policy that only allows our own files and the
  staff page's one inline script (by its SHA-256 hash). **Test** `test_staff_page_csp_blocks_injected_scripts`
  injects a script into the live page: the browser refuses to run it. `test_csp_hash_matches_the_staff_page_script`
  makes sure the hash follows any change to the page.
- CSV exports were already protected against spreadsheet formulas (`=`, `+`, `-`, `@`).

### 2. SQL injection
All values go to SQLite as parameters (`?`). Table and column names are only ever constants from the code: the
staff API checks `kind` against a fixed list before using it, exports check against a fixed list, and the ticket
reference must match `T-` and digits.
- **Tests** `test_sql_injection_in_staff_api_is_refused`, `test_sql_injection_through_the_chat_tools`: injection in the
  table name, the reference, the export name, a ticket reference, a name (refused: letters only) and a concern
  description (stored as plain text; the tables are untouched).

### 3. CSRF (another website making a logged-in staff member's browser act)
- Staff actions (status change, run reminders, resend email) need the `X-Requested-With: staff-page` header, which a
  form or image on another website cannot send, and they read JSON, which a cross-site form cannot send.
- The login cookie is `SameSite=Strict`, so other websites' requests do not carry it at all.
- CORS allows only `Content-Type`, so even a website listed in `ALLOWED_ORIGINS` cannot send the staff header, and
  credentials are never allowed cross-site.
- **Tests** `test_staff_actions_need_the_staff_page_header`, `test_embed_browser.py::test_server_answers_cors_only_for_the_allowed_origin`.
- **Fix:** a cross-site form post to a staff endpoint crashed the validation error handler (500), because it tried to
  echo the raw form bytes. Error replies now give only the field and the message, never the input.
- Not protected: logout and the login form itself (an attacker could log a staff member out, or into the same shared
  account). Low impact; noted under "What remains".

### 4. Cookie flags
`staff_session`: random 256-bit token, `HttpOnly`, `SameSite=Strict`, `Path=/staff`, `Max-Age` 8 hours, `Secure`
when served over HTTPS (behind Caddy, uvicorn's proxy headers make the app see HTTPS).
**Tests** `test_login_cookie_flags`, `test_login_cookie_is_secure_over_https`.

### 5. Security headers (fix)
New `backend/app/security.py` adds: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` (no camera, microphone, location),
`Strict-Transport-Security` over HTTPS, and on the staff pages and API a strict `Content-Security-Policy` and
`Cache-Control: no-store` (also on `/chat` and `/consent`, which can contain names and numbers).
**Tests** `test_every_response_has_basic_security_headers`, `test_https_gets_hsts`,
`test_staff_pages_have_strict_csp_and_no_caching`. The widget, demo and embed browser tests still pass with them.

### 6. Login brute force (fix)
Already: 5 wrong passwords per IP address in 15 minutes block that address; constant-time comparison.
- **Fix:** 50 wrong passwords from all addresses together in 15 minutes block all logins for the rest of the window
  (an attacker with many addresses). Trade-off: such an attack also locks out staff for up to 15 minutes.
- **Fix:** the staff login stays switched off if `ADMIN_PASSWORD` is shorter than 12 characters.
- **Tests** `test_short_password_switches_login_off`, `test_failures_from_many_addresses_block_all_logins`,
  `test_old_failures_expire`, plus the existing per-IP test.

### 7. Leaking other people's data (API and logs)
- Ticket status needs the reference and the registered mobile; a wrong number and a missing ticket get the same
  answer; 5 failures lock lookups for that chat (and the simulated-users test checks the live model too).
- Staff data and exports need login (`test_staff_data_and_exports_need_login`).
- Logs: phone numbers are masked by a filter, message text is never logged, and names are not logged.
  **Test** `test_logs_never_contain_names_or_numbers` runs a full enquiry and ticket and searches the log.
- **Fix:** error replies no longer echo the input (see 3).
- **Fix:** the automatic API pages (`/docs`, `/redoc`, `/openapi.json`) are switched off when `DEMO_MODE=false`
  (override with `API_DOCS`). **Tests** `test_api_docs_are_off_when_live`, `test_api_docs_are_on_in_demo_mode`.
- **Fix:** chat session ids. The id is the only key to a chat's history. `crypto.randomUUID` only exists on HTTPS
  pages; on a plain-http school page the widget fell back to `Math.random`, which is predictable. It now uses
  `crypto.getRandomValues` (128 bits). **Test** `test_session_id_is_random_without_randomuuid`.

### 8. Secrets in the repository or git history
- `.env` is in `.gitignore` and has never been committed (`git log --all -- .env` is empty).
- The whole history was searched for key patterns (Google `AIza...`, Anthropic `sk-ant-...`, `sk-...`, GitHub tokens,
  private keys) and for `API_KEY/PASSWORD/SECRET/TOKEN = value` lines: nothing found apart from the test passwords.
- The real Gemini key from `.env` was searched for in every file of the project and the history: found only in `.env`.
- `.dockerignore` keeps `.env` out of the Docker image; the database has no password or key columns
  (`test_database_file_has_no_secrets`).

### 9. CORS
`ALLOWED_ORIGINS` is an exact list; methods GET and POST; only the `Content-Type` header; no credentials.
- **Fix:** `*` (every website) and addresses with a path are now ignored with a warning in the log, and plain `http://`
  addresses (other than localhost) get a warning. **Test** `test_cors_refuses_wildcards_and_paths`.

### 10. Packages
`pip-audit -r requirements.txt` (22 Oct 2026): no known vulnerabilities.

## What remains (not fixed)

1. **One shared staff password**, no per-person accounts, no two-factor login, and no record of who changed what.
   Before many staff use it, add personal accounts (or put `/staff` behind the school's Google/Microsoft login).
2. **Staff logins and rate limits are kept in memory**: a restart logs staff out and resets the limits.
3. **Logout and login are not CSRF-protected** (SameSite=Strict covers most cases); impact is low with one shared account.
4. **Records are kept forever.** The privacy notice says 12 months, but nothing deletes old enquiries, tickets, callbacks
   or outbox emails yet (chat sessions are deleted after 2 hours idle). Add a nightly clean-up before real use.
5. **The per-IP rate limit depends on the proxy set-up** (see the X-Forwarded-For test in docs/progress.md, item 5).
   Someone with many addresses can still use up the AI quota; a daily cap on chats would limit the cost.
6. **Prompt injection** can still change the bot's wording; saving, consent, confirmation and lookups are enforced in code.
7. **Package versions are not pinned** (`requirements.txt` has names only). Pin them (`pip freeze`) before deploying so
   the server gets exactly the tested versions, and re-run `pip-audit` monthly.
8. **Backups contain personal data**; they must be stored where only authorised staff can open them.
9. **A hacked school website** could read the chat in its own page (the widget runs inside it). This cannot be fixed
   from the chatbot side.
