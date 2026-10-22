# Runbook: what to do when something goes wrong

For the person who runs the chatbot. Commands are given for the Docker set-up (docs/deploy.md) and, where different,
for running it directly on Windows (README). Run Docker commands in the project folder on the server.

**First, always:** open `https://<your chatbot address>/health`. `{"status":"ok", ..., "database":"ok"}` means the
server and database are fine (it does not test the AI or email). Then read the log (section 7).

---

## 1. The bot says "I'm having trouble right now. Please call the front office."

This reply means the AI service did not answer. Visitors still see the front office number, but no enquiries or
concerns can be saved until it is fixed.

1. Read the log and look for `Provider failed` (section 7):
   ```bash
   docker compose logs --since 30m chatbot | grep -i "provider"
   ```
2. What the message means:

   | Log says | Cause | Fix |
   |---|---|---|
   | `429 (daily quota used up)` | The AI's daily limit is used | Section 2 |
   | `429` (without "daily") or `503` | The AI service is busy | Usually passes in minutes (the bot already retries twice). If it lasts an hour, check https://status.cloud.google.com |
   | `400` / `API key not valid` / `403` | Wrong or cancelled key | Put a valid key in `.env` (`GEMINI_API_KEY`), then restart (section 4) |
   | `404` / `model ... not found` | The model name is wrong or the model was retired | Set `MODEL_NAME` in `.env` to a current model (https://ai.google.dev/gemini-api/docs/models), restart, run `python scripts/compare_models.py <name> --only 1 2` |
   | `Gemini request failed: ConnectError` / `getaddrinfo` | The server has no internet | Check the server's network |
   | `timed out` / `504` | The AI took too long | Try again; if it keeps happening, try another model |
   | `Could not create the AI provider` | A setting is missing | Check `LLM_PROVIDER`, `MODEL_NAME` and the key in `.env` |

3. After a fix, check with one message: `python scripts/docker_check.py --url https://<your address>` (it sends one
   chat message and checks the staff login), or ask "What are the school timings?" on the website.

## 2. The AI quota runs out

The Gemini **free tier** has a daily limit per model. It resets at **midnight Pacific time** (12:30 or 13:30 in India,
depending on the time of year). The log says `429 (daily quota used up)`.

Choose one:
- **Wait** for the reset. Visitors see "I'm having trouble ... call the front office" until then.
- **Switch model for today**: another model has its own limit. Set `MODEL_NAME` in `.env`, restart (section 4).
  Check it first with `python scripts/compare_models.py <model-name> --only 1 2 21` (skips models whose quota is
  used up). Only use models that passed the full test (`docs/test-report.md`).
- **Move to a paid tier** (the real fix, and required before real parents use the bot): in Google AI Studio, add
  billing to the project. The key and model stay the same. Set a monthly budget alert there.

Never send real parents' details through the free tier.

## 3. Email stops

1. Open the staff page, **Outbox** box. Read the status and the error under each row:
   - `failed` with an error: the mail server refused. The chatbot retries after 1, 5, 15 and 60 minutes (5 tries).
   - `blocked`: on purpose. `TEST_MODE=true` without `TEST_RECIPIENT`, or a placeholder address (example.com) in
     `kb/<campus>/routing.json`.
   - `logged`: email is not set up (`SMTP_HOST` is empty).
2. Test the settings: `docker compose exec chatbot python scripts/send_test_email.py`
   (Windows: `python scripts/send_test_email.py`). It explains the problem in plain words. Common causes: the
   mailbox password or app password was changed or revoked; the provider's daily sending limit was reached.
3. Fix `.env`, restart (section 4), then press **Resend** on the failed rows (rows that used up their 5 tries are
   not retried by themselves).
4. Urgent safety emails are sent before everything else once email works again. If email was down for a long time,
   tell the principal to check urgent concerns on the staff page directly.

## 4. Restart

| What | Docker | Windows |
|---|---|---|
| Restart the chatbot | `docker compose restart chatbot` | In the server window press Ctrl+C, then `uvicorn backend.app.main:app` again |
| After changing `.env` | `docker compose up -d` (it picks up the change) | Ctrl+C and start again |
| After changing the code | `git pull`, then `docker compose up -d --build` | `git pull`, `pip install -r requirements.lock.txt -r requirements-dev.txt`, start again |
| Everything (also Caddy) | `docker compose down`, then `docker compose up -d` | — |

A restart logs staff out and resets the rate limits. Chats, enquiries, tickets and the outbox are kept (SQLite).
Check `/health` afterwards.

## 5. Restore a backup

Only if the database is lost or damaged. Full steps: docs/deploy.md, section 8, "Restore". In short:

```bash
docker compose exec chatbot ls /app/data/backups          # pick a backup
docker compose stop chatbot
docker compose run --rm chatbot python scripts/restore_db.py /app/data/backups/chatbot-YYYYMMDD-HHMMSS.db
docker compose start chatbot
```

The script checks the backup, shows how many records it holds, asks for YES, and keeps the current database as
`chatbot.before-restore-<date-time>.db` (restore that file the same way to undo). Anything that came in after the
backup was made is lost: check the outbox emails from that time.

## 6. Update the school content

1. Put the new documents in `incoming/` (never in Git) and run `python scripts/ingest_docs.py`.
2. Read `docs/content-review.md`; send the questions to the school; fix the drafts in `drafts/pilot-campus/`
   (remove every NEEDS REVIEW).
3. `python scripts/approve_kb.py` copies the drafts into `kb/` (it refuses while marks are left).
4. Update by hand if they changed: `kb/pilot-campus/routing.json` (who gets which concern, emails),
   `config/working_days.json` (holidays), `kb/school.json`.
5. `python scripts/check_kb.py --live` must say "All checks passed".
6. New test questions: `python scripts/generate_checks.py`, review, rename (README).
7. Restart the chatbot (section 4): the knowledge is read when the server starts.
8. Run `python -m pytest` and the answer-quality test (README, "Test"). Check the staff page box
   **Questions the bot could not answer** over the next days.

Small fixes (a phone number, a date): edit the file in `kb/pilot-campus/` directly, run `check_kb.py --live`, restart.

## 7. See the logs

| What | Docker | Windows |
|---|---|---|
| Live log | `docker compose logs -f chatbot` (Ctrl+C to stop) | the server window |
| Last hour | `docker compose logs --since 1h chatbot` | — |
| Only problems | `docker compose logs --since 1h chatbot \| grep -E "WARNING\|ERROR"` | — |
| Caddy (HTTPS) | `docker compose logs caddy` | — |

The log never contains message text, names or full phone numbers (numbers are shown as 98******10).

What the important lines mean:

| Line | Meaning |
|---|---|
| `Provider failed: ...` | The AI did not answer (section 1) |
| `Email N to <role> failed (try X of 5)` | Email problem (section 3) |
| `Possible attack on the staff login: ...` | Many wrong staff passwords from many addresses. Wrong attempts are slowed down; nobody is locked out. If it goes on for hours, change `ADMIN_PASSWORD` and restart |
| `Staff login blocked for <address>` | One address typed 5 wrong passwords; it can try again after 15 minutes |
| `Rate limit hit for a chat session` | Someone sent messages very fast; they were asked to wait a minute |
| `Setting problem: ...` | A mistake in `.env`; read the message |
| `Reply had N contact detail(s) not in the knowledge` | The AI made up an email or phone number and was corrected; if frequent, check the model |
| `Reminder job made N notification(s)` | Normal: reminders or escalations were sent |
| `Retention purge ... deleted ...` | Normal: the nightly clean-up ran |

## 8. Regular checks

- Daily: the staff page (urgent concerns, failed emails, the red banner).
- Weekly: copy backups off the server (docs/deploy.md, section 8); look at "Questions the bot could not answer".
- Monthly: `pip-audit -r requirements.lock.txt`; restore one backup on a test computer to be sure backups work.
