# School Chatbot Project: context for Claude Code

Read this file at the start of every session. It is the project's memory.

## Project motto (never change without asking)
Use AI and automation to make school services easier to access:
1. Reduce repetitive work
2. Improve the way people get information from the school

## Who and when
- One developer (first-time builder). Explain steps simply and in small pieces.
- Started 15 Oct 2026. Deadline 3 Nov 2026 (20 days, working every day).
- Client: Sri Vidya schools. They have an ERP and a website only. The chatbot is built from scratch.

## Scope for the 20 days
- Website chat only. English only. One pilot campus fully loaded.
- User group 1: prospective parents, students seeking admission, guardians, visitors.
- User group 2: existing parents, students, teachers and authorised staff (public information only for now).
- Priority 1: answers from approved content (admissions, fees, documents, curriculum, calendar, holidays, PTM, transport info, contacts).
- Priority 2: enquiry capture (validated fields), duplicate detection, route to campus counsellor, email reminders and escalation, visit/counselling request, simple staff view.
- Priority 3: light tickets (log concern, category, ticket ID, route to role, status lookup, auto-escalate).
- Out of scope now: Telugu, Hindi, WhatsApp, login/OTP, ERP-based data (fee receipts, per-child routes, results), business/vendor group, surveys and analytics.

## Rules for the bot
- Answer ONLY from approved content in kb/. If unsure, say so and offer a human handoff.
- Never promise discounts, admission or dates that are not in approved content.
- Never reveal student or parent personal data. One parent's data must never reach another.
- Safety, health and bullying topics go straight to a human.
- Call concerns "suggestions" or "share a concern", never "complaints".
- Campus-aware: ask which campus first; keep content separate per campus.

## Rules for the code
- Keep it simple. Small steps. Run and test after each step.
- Never put secrets in code or Git. Use .env (see .env.example).
- Add a short note to docs/decisions.md for every important choice.

## Proposed stack (confirm in docs/decisions.md)
Python 3.11+, FastAPI backend, SQLite for the pilot, plain JavaScript chat widget (one script tag), Claude API for answers with the approved content supplied in the prompt.

## Demo data mode (current)
- The school team is on leave, so all content in kb/ is DUMMY (fictional school, fake numbers, example.com emails).
- Keep content separate from code so the real files can be swapped in. Never hardcode school facts in code.
- A config flag DEMO_MODE=true must show a visible 'Demo' note in the chat window and in staff views, so dummy answers are never mistaken for real ones.
- docs/test-questions.csv is the accuracy test. Re-run it after swapping in real content.
- ERP integration and WhatsApp are skipped for now.
