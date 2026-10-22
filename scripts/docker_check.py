"""Check a running chatbot (for example the Docker set-up on http://localhost) in one go.

Usage (after: $env:CHATBOT_DOMAIN="http://localhost"; docker compose up -d --build):
    python scripts/docker_check.py                        # checks http://localhost
    python scripts/docker_check.py --url http://localhost --no-chat

Checks:
1. /health answers "ok" with the database "ok".
2. One chat message gets a real reply (uses one AI request; skip with --no-chat).
3. The staff login works with ADMIN_PASSWORD from .env.
4. Fake X-Forwarded-For headers are ignored: 41 quick requests, each pretending to come from a different address,
   must still hit the per-address limit (CHAT_LIMIT_PER_IP, default 40 a minute). Wait a minute before chatting again.
Exit code 0 = all passed."""
import argparse
import os
import sys
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def run(url: str, password: str, chat: bool, limit: int) -> list[tuple[str, bool, str]]:
    results = []
    with httpx.Client(base_url=url, timeout=60, follow_redirects=False) as c:
        try:
            h = c.get("/health")
            ok = h.status_code == 200 and h.json().get("database") == "ok"
            results.append(("health", ok, h.text[:120]))
        except httpx.HTTPError as e:
            return [("health", False, f"cannot reach {url}: {e}")]

        if chat:
            r = c.post("/chat", json={"session_id": f"check-{uuid.uuid4().hex}", "message": "Hello"})
            reply = r.json().get("reply", "") if r.headers.get("content-type", "").startswith("application/json") else ""
            ok = r.status_code == 200 and reply and "having trouble" not in reply
            results.append(("chat", bool(ok), reply[:120] or f"HTTP {r.status_code}"))

        if password:
            r = c.post("/staff/login", data={"password": password})
            ok = r.status_code == 303 and "staff_session" in r.headers.get("set-cookie", "")
            results.append(("staff login", ok, f"HTTP {r.status_code}"))
        else:
            results.append(("staff login", False, "ADMIN_PASSWORD is empty in .env"))

        codes = []
        for n in range(limit + 1):
            r = c.post("/consent", json={"session_id": f"check-{uuid.uuid4().hex}", "agree": False},
                       headers={"X-Forwarded-For": f"203.0.113.{n % 250}"})
            codes.append(r.status_code)
        blocked = 429 in codes
        results.append(("fake X-Forwarded-For ignored", blocked,
                        f"{codes.count(200)} accepted, {codes.count(429)} refused (refused means the limit held)"))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost")
    parser.add_argument("--no-chat", action="store_true")
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    password = os.getenv("ADMIN_PASSWORD", "").strip()
    limit = int(os.getenv("CHAT_LIMIT_PER_IP", "").strip() or 40)
    results = run(args.url.rstrip("/"), password, not args.no_chat, limit)
    for name, ok, detail in results:
        print(f"  [{'x' if ok else ' '}] {name}: {detail}")
    passed = all(ok for _, ok, _ in results)
    print("All checks passed." if passed else "Some checks failed (see above).")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
