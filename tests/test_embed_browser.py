"""Real-site embed test: docs/embed-test.html is served from a different origin than the chatbot and loads the
chat window with one script tag, in headless Chrome (Chromium if Chrome is not installed).
One website origin is in ALLOWED_ORIGINS, a second one is not. Uses the FakeLLM; saves screenshots."""
import http.server
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

playwright = pytest.importorskip("playwright.sync_api")

from tests.test_widget_browser import free_port  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screenshots"
PAGE = (ROOT / "docs" / "embed-test.html").read_text(encoding="utf-8")


def serve_website(api_url: str) -> tuple[str, http.server.ThreadingHTTPServer]:
    """A pretend school website on its own port, serving embed-test.html with the script tag pointing at api_url."""
    html = PAGE.replace("http://localhost:8000", api_url).encode()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200 if self.path == "/embed-test.html" else 404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html if self.path == "/embed-test.html" else b"not found")

        def log_message(self, *args):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", free_port()), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://localhost:{httpd.server_address[1]}", httpd


@pytest.fixture(scope="module")
def sites(tmp_path_factory):
    api_port = free_port()
    api = f"http://127.0.0.1:{api_port}"
    allowed, allowed_httpd = serve_website(api)
    blocked, blocked_httpd = serve_website(api)
    env = {**os.environ, "LLM_PROVIDER": "fake", "DEMO_MODE": "true", "ALLOWED_ORIGINS": allowed,
           "DB_PATH": str(tmp_path_factory.mktemp("db") / "embed.db"), "SMTP_HOST": ""}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app.main:app", "--port", str(api_port)],
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            if httpx.get(api + "/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("server did not start")
    yield {"api": api, "allowed": allowed, "blocked": blocked}
    proc.kill()
    allowed_httpd.shutdown()
    blocked_httpd.shutdown()


@pytest.fixture(scope="module")
def chrome():
    with playwright.sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome")  # the installed Google Chrome, headless
        except Exception:
            browser = p.chromium.launch()
        yield browser
        browser.close()


def open_page(chrome, url, width=1280, height=800):
    page = chrome.new_page(viewport={"width": width, "height": height})
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(url + "/embed-test.html")
    return page, errors


def test_chat_works_on_an_allowed_website(sites, chrome):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page, errors = open_page(chrome, sites["allowed"])
    # The widget really comes from another origin, with one script tag.
    assert page.evaluate("[...document.scripts].filter(s => s.src).map(s => new URL(s.src).origin)") == [sites["api"]]
    assert page.evaluate("location.origin") != sites["api"]

    page.locator(".sc-launcher").click()
    page.get_by_text("Hello! I'm the School Assistant").wait_for()
    page.get_by_role("button", name="Campus A").click()   # campuses come from /config on the chatbot server
    page.get_by_role("button", name="I'm exploring admissions").click()
    page.locator(".sc-form input").fill("What are the school timings?")
    page.locator(".sc-form input").press("Enter")
    page.get_by_text("This is a scripted test reply.").wait_for()
    assert page.locator(".sc-msg.sc-error").count() == 0
    assert page.locator(".sc-demo").is_visible()           # Demo label shown (DEMO_MODE=true)
    # The school site's own styles (uppercase Georgia buttons and inputs) must not leak into the chat window.
    assert page.evaluate("getComputedStyle(document.querySelector('.sc-form input')).textTransform") == "none"
    page.screenshot(path=str(SHOTS / "7-embed-allowed-site.png"))
    assert errors == []

    # Phone size: no sideways scrolling on the school site with the chat open.
    phone, _ = open_page(chrome, sites["allowed"], 400, 800)
    phone.locator(".sc-launcher").click()
    phone.get_by_text("Hello! I'm the School Assistant").wait_for()
    assert phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_chat_is_blocked_on_a_website_not_in_allowed_origins(sites, chrome):
    page, errors = open_page(chrome, sites["blocked"])
    page.locator(".sc-launcher").click()
    page.locator(".sc-form input").fill("What are the school timings?")
    page.locator(".sc-form input").press("Enter")
    page.locator(".sc-msg.sc-error").wait_for()
    assert "I'm having trouble right now" in page.locator(".sc-msg.sc-error").inner_text()
    assert page.get_by_text("This is a scripted test reply.").count() == 0
    assert any("CORS" in e for e in errors), errors
    page.screenshot(path=str(SHOTS / "8-embed-blocked-site.png"))


def test_server_answers_cors_only_for_the_allowed_origin(sites):
    def preflight(origin):
        return httpx.options(sites["api"] + "/chat", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type"})
    assert preflight(sites["allowed"]).headers.get("access-control-allow-origin") == sites["allowed"]
    assert "access-control-allow-origin" not in preflight(sites["blocked"]).headers
    assert "access-control-allow-origin" not in preflight("https://evil.example").headers
    # Even the allowed website may not send the staff page's header (so it cannot drive staff actions),
    # and credentials (the staff cookie) are never allowed cross-site.
    staff = httpx.options(sites["api"] + "/staff/api/status", headers={
        "Origin": sites["allowed"], "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-requested-with"})
    assert staff.status_code == 400 and "x-requested-with" not in staff.headers.get("access-control-allow-headers", "")
    assert "access-control-allow-credentials" not in preflight(sites["allowed"]).headers
