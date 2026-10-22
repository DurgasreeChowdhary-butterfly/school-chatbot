"""The Docker files stay consistent, and scripts/docker_check.py works against a server run like the image."""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

from scripts.docker_check import run
from tests.test_widget_browser import free_port

ROOT = Path(__file__).resolve().parents[1]


def test_compose_trusts_exactly_caddys_address():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    trusted = re.search(r"FORWARDED_ALLOW_IPS: (\S+)", compose).group(1)
    caddy = re.search(r"caddy:.*?ipv4_address: (\S+)", compose, re.S).group(1)
    assert trusted == caddy == "${CADDY_IP:-172.30.0.2}"
    assert "${CHATBOT_SUBNET:-172.30.0.0/24}" in compose
    assert '"*"' not in (ROOT / "Dockerfile").read_text(encoding="utf-8").split("CMD")[-1]
    chatbot_section = compose.split("caddy:")[0]
    assert "ports:" not in chatbot_section  # the app is never opened directly


def test_docker_check_script_against_a_server_run_like_the_image(tmp_path):
    port = free_port()
    env = {**os.environ, "LLM_PROVIDER": "fake", "DB_PATH": str(tmp_path / "c.db"), "ADMIN_PASSWORD": "check-password-1",
           "CHAT_LIMIT_PER_IP": "5", "FORWARDED_ALLOW_IPS": "127.0.0.2"}  # trusted proxy is not the test client
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app.main:app", "--port", str(port),
                             "--proxy-headers"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                if httpx.get(url + "/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        results = run(url, "check-password-1", chat=True, limit=5)
    finally:
        proc.kill()
    assert [(name, ok) for name, ok, _ in results] == [
        ("health", True), ("chat", True), ("staff login", True), ("fake X-Forwarded-For ignored", True)]
