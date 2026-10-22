# Deploying the school chatbot (step by step)

This guide is for someone doing it for the first time. Nothing here has been deployed yet: follow it when the
school has chosen a server. Do every step in order. Commands are typed in a terminal on the server.

> **Before real parents use it:** the AI must be on a **paid** provider or tier (not the Gemini free tier),
> `DEMO_MODE=false`, `TEST_MODE=false`, and `python scripts/check_kb.py --live` must pass. See step 10.

## What the finished set-up looks like

```
Parent's browser ──HTTPS──> Caddy (ports 80 and 443, gets the certificate) ──> chatbot (port 8000, inside Docker)
                                                                                     └── SQLite database (Docker volume)
School website page ── loads https://chat.yourschool.in/widget/chat.js (one script tag)
```

Two programs run in Docker: **chatbot** (this project) and **Caddy** (a web server that handles HTTPS for you).

## 1. What you need

- A server (a small cloud machine is enough: 1 CPU, 1 GB memory, Linux such as Ubuntu 24.04).
- **Docker** with the compose plugin on that server (`docker --version` and `docker compose version` should both work).
- A **domain name for the chatbot**, for example `chat.yourschool.in`. Ask whoever manages the school's domain to add
  a DNS **A record** for it pointing to the server's IP address. Wait until `ping chat.yourschool.in` shows that IP.
- Ports **80 and 443** open to the internet on the server's firewall (Caddy needs both to get the HTTPS certificate).
- The approved school content (see README, "Replace the dummy content").

## 2. Copy the project to the server

```bash
git clone <the project's Git address> school-chatbot
cd school-chatbot
```

The `.env` file is never in Git (it holds passwords). You create it in the next step.

## 3. Create the .env file (environment variables)

```bash
cp .env.example .env
nano .env        # or any text editor
```

Fill in these values. Keep `.env` private: only the person running the server should be able to read it
(`chmod 600 .env`).

| Variable | What to put | Notes |
|---|---|---|
| `CHATBOT_DOMAIN` | `chat.yourschool.in` | Add this line yourself. Caddy gets the HTTPS certificate for it |
| `LLM_PROVIDER` | `gemini` or `anthropic` | Must be a **paid** tier/provider before real data |
| `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | the key for that provider | Never put keys anywhere else |
| `MODEL_NAME` | the model, e.g. `gemini-3.5-flash-lite` | Compare models first with `scripts/compare_models.py` |
| `LLM_TEMPERATURE` | leave empty | Google recommends the default for Gemini 3 (docs/consistency-report.md) |
| `DEMO_MODE` | `true` while testing, `false` when live | `false` removes the "Demo" labels |
| `ADMIN_PASSWORD` | a long password (16+ characters) | For the staff page `/staff`. Empty = staff page off |
| `ALLOWED_ORIGINS` | `https://www.yourschool.in,https://yourschool.in` | Every website address that shows the chat (step 7) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY` | from the email provider, e.g. `smtp.gmail.com`, `587`, `starttls` | Empty `SMTP_HOST` = no email, outbox only |
| `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | the sending mailbox and its (app) password | Use a dedicated mailbox, e.g. chatbot@yourschool.in |
| `TEST_MODE` | `true` at first, `false` when the school approves real sending | `true` sends every email to `TEST_RECIPIENT` only |
| `TEST_RECIPIENT` | your own email address | Used while `TEST_MODE=true` |
| `COUNSELLOR_EMAIL_PILOT` | optional | Overrides the counsellor email in routing.json |
| `CHAT_LIMIT_PER_SESSION`, `CHAT_LIMIT_PER_IP`, `HISTORY_LIMIT` | leave the defaults (12, 40, 20) | Raise the IP limit if many parents share one school network |

`DB_PATH` is set by `docker-compose.yml` (the database lives in a Docker volume); do not set it in `.env`.

## 4. HTTPS

You do not need to buy or copy a certificate. Caddy (configured in `deploy/Caddyfile`) asks Let's Encrypt for a free
certificate for `CHATBOT_DOMAIN` the first time it starts, and renews it by itself. It needs:
- the DNS record from step 1 to already point at the server, and
- ports 80 and 443 open.

The chatbot itself (port 8000) is **not** opened to the internet: only Caddy can reach it. Do not add a `ports:` line
for the chatbot. Caddy has a fixed address on a private Docker network (172.30.0.2), and the chatbot believes the
visitor address only when it comes from Caddy (`FORWARDED_ALLOW_IPS` in docker-compose.yml). So nobody can fake their
address to get around the per-IP rate limit (`tests/test_proxy_headers.py` proves this). If 172.30.0.0/24 is already
used on the server, change the subnet and both addresses together.

## 5. Start it

```bash
docker compose up -d --build
```

The first time takes a few minutes (it downloads Python and Caddy and installs the packages).

## 6. Check the server is healthy

1. `docker compose ps`: both `chatbot` and `caddy` should be "running", and the chatbot should say `(healthy)`
   after about 30 seconds. Docker checks `/health` every 30 seconds by itself.
2. In a browser open `https://chat.yourschool.in/health`. You should see
   `{"status":"ok","demo":true,"database":"ok"}` (with `"demo":false` once live). A padlock in the address bar means
   HTTPS works. If the database cannot be read you get status 503 and `"database":"error"`.
3. Open `https://chat.yourschool.in/demo` and ask a question, e.g. "What are the school timings?".
4. Open `https://chat.yourschool.in/staff` and log in with `ADMIN_PASSWORD`.
5. Read the log if something is wrong: `docker compose logs -f chatbot` (Ctrl+C to stop reading).
   Phone numbers are masked in the log and messages are never logged.

A free uptime monitor (for example UptimeRobot) can open `/health` every 5 minutes and email you if it stops
answering "ok".

## 7. Add the chat to the school website

Ask whoever edits the school website to add **one line** just before `</body>` on each page that should show the chat:

```html
<script src="https://chat.yourschool.in/widget/chat.js" defer></script>
```

Optional extras on the same tag: `data-campus="pilot-campus"` (skip the campus question on a campus page),
`data-open="true"` (open the chat straight away), `data-theme="light"` or `"dark"`.

Then allow that website in `.env`:

```
ALLOWED_ORIGINS=https://www.yourschool.in,https://yourschool.in
```

- An "origin" is `https://` + the address, **without** a path or a `/` at the end.
- List every address the website opens on (with and without `www`, and any test site).
- Restart after changing `.env`: `docker compose up -d` (it notices the change).

If an address is missing, the chat window opens but every message fails, and the browser's developer console
(F12) shows a "CORS" error. The test page `docs/embed-test.html` shows how this looks, and the automated test `tests/test_embed_browser.py`
checks both an allowed and a blocked website.

## 8. Database backups

All enquiries, tickets, callbacks, the outbox and open chats are in one SQLite file inside the `chatbot-data` volume.

Make a backup (safe while the server is running):

```bash
docker compose exec chatbot python scripts/backup_db.py
```

It writes `/app/data/backups/chatbot-YYYYMMDD-HHMMSS.db`, checks it, and keeps the newest 30 copies.

**Every night automatically:** run `crontab -e` on the server and add this line (02:30 every night):

```
30 2 * * * cd /home/<you>/school-chatbot && docker compose exec -T chatbot python scripts/backup_db.py >> backup.log 2>&1
```

**Copy backups off the server** at least once a week (a server can fail), for example:

```bash
docker compose cp chatbot:/app/data/backups ./backups-copy
```

then move `backups-copy` to the school's protected storage. Backups contain parents' names and mobile numbers: only
authorised staff may have access, and copies older than the privacy notice allows (12 months) must be deleted.

**Restore** (only if the database is lost or damaged):

```bash
docker compose stop chatbot
docker compose cp ./backups-copy/chatbot-20261101-023000.db chatbot:/app/data/chatbot.db
docker compose start chatbot
```

Then check `/health` and the staff page.

## 9. Changing content or code later

- **New or corrected school content:** replace the files in `kb/` (and `config/working_days.json` for holidays), run
  `python scripts/check_kb.py --live` on your computer or the server, then `docker compose restart chatbot`.
  No rebuild is needed: `kb/` and `config/` are read from the server's folders.
- **New version of the code:** `git pull`, then `docker compose up -d --build`. The database volume is kept.

## 10. Before real parents use it (checklist)

- [ ] AI provider is a paid tier or provider whose terms suit the school's privacy rules (not the Gemini free tier)
- [ ] All kb/ files replaced with school-approved content, `privacy_notice.md` approved
- [ ] `python scripts/check_kb.py --live` says "All checks passed"
- [ ] `docs/test-checks.json` updated with the real facts, and the 40-question test run (`scripts/run_test_questions.py`)
- [ ] `DEMO_MODE=false`, `TEST_MODE=false`, real staff emails in `routing.json`, one test email per role received
- [ ] Long `ADMIN_PASSWORD`, `.env` readable only by the server admin
- [ ] `/health` is ok over HTTPS, the chat works from the real website, nightly backup runs and a copy was restored once as a test

## Troubleshooting

| What you see | What to do |
|---|---|
| Caddy log says it cannot get a certificate | The DNS record does not point at the server yet, or port 80/443 is blocked |
| Chat opens on the website but every message fails | The website's address is missing from `ALLOWED_ORIGINS` (step 7) |
| "I'm having trouble right now" for every message | The AI key, model name or quota. `docker compose logs chatbot` shows the provider error |
| Staff page says login is switched off | `ADMIN_PASSWORD` is empty in `.env` |
| Outbox rows say `blocked` | `TEST_MODE=true` without `TEST_RECIPIENT`, or the address is a placeholder (example.com) |
| Outbox rows say `failed` | Wrong SMTP settings or password; fix `.env`, restart, then press Resend on the staff page |
| Container keeps restarting | `docker compose logs chatbot`: often a mistake in `config/working_days.json` (the message says which) |

Running without Docker (for example on a school Windows server) is possible: install Python 3.12, follow the README
set-up, start with `uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --proxy-headers`, and put a web server
with HTTPS (IIS, Caddy or nginx) in front of it. The Docker set-up above is simpler to keep running.
