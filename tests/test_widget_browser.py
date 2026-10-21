"""Chat window test in a real (headless) browser. Starts its own server with the FakeLLM.
Saves screenshots to docs/screenshots/. Skipped if Playwright is not installed."""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

playwright = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screenshots"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    port = free_port()
    env = {**os.environ, "LLM_PROVIDER": "fake", "DEMO_MODE": "true",
           "DB_PATH": str(tmp_path_factory.mktemp("db") / "browser.db")}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            if httpx.get(url + "/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("server did not start")
    yield url
    proc.kill()


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def bot_messages(page):
    return page.locator(".sc-msg.sc-bot:not(.sc-typing)")


def no_horizontal_scroll(page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def walk_opening_flow(page, base_url):
    page.goto(base_url + "/demo")
    page.locator(".sc-panel").wait_for(state="visible")
    page.get_by_text("Hello! I'm the School Assistant").wait_for()
    page.get_by_role("button", name="Campus A").click()
    page.get_by_role("button", name="I'm exploring admissions").click()
    page.get_by_role("button", name="Fees").wait_for()


def test_opening_flow_and_question(server, browser):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    walk_opening_flow(page, server)
    assert page.locator(".sc-demo").is_visible(), "Demo label should show while DEMO_MODE=true"
    assert page.get_by_role("button", name="Talk to a person").is_visible()
    page.screenshot(path=SHOTS / "1-opening-flow-desktop.png")

    before = bot_messages(page).count()
    page.locator(".sc-form input").fill("What is the minimum age for Grade 1?")
    page.locator(".sc-form button").click()
    page.locator(".sc-msg.sc-you", has_text="minimum age").wait_for()
    page.wait_for_function(f"document.querySelectorAll('.sc-msg.sc-bot:not(.sc-typing)').length > {before}")
    assert "scripted test reply" in bot_messages(page).last.inner_text()
    page.get_by_role("button", name="Menu").wait_for()
    page.screenshot(path=SHOTS / "2-question-and-reply-desktop.png")

    # A page reload keeps the conversation (sessionStorage).
    count = bot_messages(page).count()
    page.reload()
    page.locator(".sc-msg.sc-you", has_text="minimum age").wait_for()
    assert bot_messages(page).count() == count
    page.close()


def test_phone_width_has_no_horizontal_scroll(server, browser):
    page = browser.new_page(viewport={"width": 400, "height": 820}, is_mobile=True, has_touch=True)
    walk_opening_flow(page, server)
    assert no_horizontal_scroll(page)
    box = page.locator(".sc-panel").bounding_box()
    assert box["width"] <= 400
    page.screenshot(path=SHOTS / "3-phone-400px.png")
    page.locator(".sc-close").click()
    assert page.locator(".sc-launcher").is_visible()
    assert no_horizontal_scroll(page)
    page.close()


def test_dark_theme(server, browser):
    context = browser.new_context(color_scheme="dark", viewport={"width": 1280, "height": 800})
    page = context.new_page()
    walk_opening_flow(page, server)
    bg = page.evaluate("getComputedStyle(document.querySelector('.sc-panel')).backgroundColor")
    assert bg == "rgb(23, 32, 51)"  # --sc-surface in the dark theme
    page.screenshot(path=SHOTS / "4-dark-theme.png")
    context.close()


def test_vendor_choice_asks_the_backend(server, browser):
    page = browser.new_page()
    page.goto(server + "/demo")
    page.get_by_role("button", name="Campus A").click()
    page.get_by_role("button", name="Business or vendor enquiry").click()
    page.get_by_text("scripted test reply").wait_for()
    page.close()
