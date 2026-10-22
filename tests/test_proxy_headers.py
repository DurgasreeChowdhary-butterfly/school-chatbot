"""The per-IP rate limit must key on the real client address, and a client must not be able to dodge it by
sending its own X-Forwarded-For header. Runs uvicorn exactly as the Docker image does (proxy headers on), with
127.0.0.2 standing in for Caddy (the only trusted proxy) and 127.0.0.1 for a client that connects directly.
Uses /consent (rate limited like /chat, no AI calls). Docker itself is not needed for this test."""
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest

from tests.test_widget_browser import free_port

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 3  # CHAT_LIMIT_PER_IP for these servers


def start(tmp_path, trusted: str) -> tuple[str, subprocess.Popen]:
    port = free_port()
    env = {**os.environ, "LLM_PROVIDER": "fake", "DB_PATH": str(tmp_path / f"proxy-{port}.db"),
           "CHAT_LIMIT_PER_IP": str(LIMIT), "CHAT_LIMIT_PER_SESSION": "100", "FORWARDED_ALLOW_IPS": trusted}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1",
                             "--port", str(port), "--proxy-headers"], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            if httpx.get(url + "/health", timeout=1).status_code == 200:
                return url, proc
        except httpx.HTTPError:
            time.sleep(0.2)
    proc.kill()
    pytest.fail("server did not start")


def consent(url: str, source: str, forwarded: str | None) -> int:
    client = httpx.Client(transport=httpx.HTTPTransport(local_address=source))
    headers = {"X-Forwarded-For": forwarded} if forwarded else {}
    body = {"session_id": f"proxy-{uuid.uuid4().hex}", "agree": True}
    return client.post(url + "/consent", json=body, headers=headers).status_code


@pytest.fixture
def behind_proxy(tmp_path):
    url, proc = start(tmp_path, "127.0.0.2")  # like docker-compose: trust only the proxy's address range
    yield url
    proc.kill()


def test_direct_client_cannot_dodge_the_limit_with_a_fake_header(behind_proxy):
    codes = [consent(behind_proxy, "127.0.0.1", f"203.0.113.{n}") for n in range(LIMIT + 2)]
    assert codes[:LIMIT] == [200] * LIMIT and codes[LIMIT:] == [429, 429]  # the fake addresses were ignored


def test_limit_uses_the_real_client_address_added_by_the_proxy(behind_proxy):
    # Caddy forwards: the client's own (fake) header value first, then the real address it saw.
    real = [consent(behind_proxy, "127.0.0.2", f"198.51.100.{n}, 192.0.2.10") for n in range(LIMIT + 1)]
    assert real[:LIMIT] == [200] * LIMIT and real[LIMIT] == 429
    other = consent(behind_proxy, "127.0.0.2", "192.0.2.99")  # a different real visitor is not blocked
    assert other == 200


def test_trusting_every_address_would_let_a_client_dodge_the_limit(tmp_path):
    """Why the old setting (--forwarded-allow-ips "*") was replaced: any client can pretend to be anyone."""
    url, proc = start(tmp_path, "*")
    try:
        codes = [consent(url, "127.0.0.1", f"203.0.113.{n}") for n in range(LIMIT + 2)]
        assert codes == [200] * (LIMIT + 2)
    finally:
        proc.kill()
