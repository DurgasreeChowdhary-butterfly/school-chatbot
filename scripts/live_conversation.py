"""Send several messages in ONE chat session to a running server and print the replies.
Useful to check multi-turn flows (enquiries, concerns) with the live model.
When the bot shows the privacy notice, this script taps "I agree" for you (like the chat window).
Usage: python scripts/live_conversation.py "first message" "second message" ...
Use dummy details only."""
import sys
import time
import uuid

import httpx

BASE = "http://127.0.0.1:8000"
session = f"live-{uuid.uuid4().hex[:16]}"
for i, message in enumerate(sys.argv[1:]):
    if i:
        time.sleep(5)  # stay inside free-tier rate limits
    reply = httpx.post(f"{BASE}/chat", json={"session_id": session, "message": message}, timeout=120).json()
    print(f"YOU: {message}\nBOT: {reply.get('reply')}\n")
    if reply.get("action") == "consent":
        httpx.post(f"{BASE}/consent", json={"session_id": session, "agree": True}, timeout=30)
        print("     [privacy notice shown; tapped I agree]\n")
