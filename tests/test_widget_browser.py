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


BROWSER_DB = {}


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    port = free_port()
    BROWSER_DB["path"] = tmp_path_factory.mktemp("db") / "browser.db"
    env = {**os.environ, "LLM_PROVIDER": "fake", "DEMO_MODE": "true", "ADMIN_PASSWORD": "browser-test",
           "DB_PATH": str(BROWSER_DB["path"])}
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


def test_consent_card(server, browser):
    import json
    page = browser.new_page(viewport={"width": 400, "height": 820}, is_mobile=True)
    walk_opening_flow(page, server)

    # The next /chat reply asks for consent (as the real backend does when the AI calls request_consent).
    def consent_reply(route):
        route.fulfill(status=200, content_type="application/json", body=json.dumps({
            "reply": "Before I take your details, please read the privacy notice below and tap I agree.",
            "demo": True, "action": "consent",
            "notice": "- We collect only what is needed.\n- Only the school staff who handle it can see them."}))
    page.route("**/chat", consent_reply, times=1)
    page.get_by_role("button", name="Book a campus visit").click()
    page.get_by_role("heading", name="Privacy notice").wait_for()
    assert no_horizontal_scroll(page)
    page.screenshot(path=SHOTS / "6-consent-card-phone.png")

    consent_calls = []
    page.on("request", lambda r: consent_calls.append(r.post_data) if r.url.endswith("/consent") else None)
    page.get_by_role("button", name="I agree").click()
    page.locator(".sc-msg.sc-you", has_text="I agree to the privacy notice").wait_for()
    page.get_by_text("scripted test reply").last.wait_for()
    assert consent_calls and '"agree": true' in consent_calls[0].replace('":true', '": true')
    assert page.locator(".sc-consent .sc-card-actions").count() == 0  # buttons removed after answering
    page.close()


def test_staff_page_login_and_status_change(server, browser):
    from backend.app import db
    from backend.app.notify import notify
    from backend.app.routing import role

    # Put sample (dummy) rows in the browser server's database.
    db.init_db(BROWSER_DB["path"])
    db.insert("enquiries", {"campus": "pilot-campus", "parent_name": "Sample Parent", "child_name": "Sample Child",
                            "class_applying": "Grade 3", "mobile": "9000000002", "visit_preference": "Saturday morning",
                            "assigned_to": "Admission counsellor"})
    t = db.insert("tickets", {"campus": "pilot-campus", "category": "Safety, health, bullying",
                              "description": "Sample: child is being bullied", "parent_name": "Sample Parent",
                              "mobile": "9000000001", "urgent": 1, "first_contact": "Principal",
                              "backup_contact": "Vice principal"})
    notify("pilot-campus", role("pilot-campus", "Principal"), f"URGENT New ticket {t['ref']}", "Sample body", t["ref"], "ticket")

    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(server + "/staff")
    page.fill("input[name=password]", "wrong")
    page.click("button[type=submit]")
    page.get_by_text("Wrong password").wait_for()
    page.fill("input[name=password]", "browser-test")
    page.click("button[type=submit]")
    page.get_by_role("heading", name="Staff view").wait_for()
    assert page.locator("#demo").is_visible()
    page.get_by_text("Sample: child is being bullied").wait_for()

    page.select_option(f"select[data-ref='{t['ref']}']", "In progress")
    page.get_by_text(f"{t['ref']}: In progress").wait_for()  # confirmation toast
    assert db.find_one("tickets", ref=t["ref"])["status"] == "In progress"
    assert no_horizontal_scroll(page)
    page.screenshot(path=SHOTS / "5-staff-view.png", full_page=True)

    phone = browser.new_page(viewport={"width": 400, "height": 820})
    phone.context.add_cookies(page.context.cookies())
    phone.goto(server + "/staff")
    phone.get_by_role("heading", name="Staff view").wait_for()
    assert no_horizontal_scroll(phone)
    phone.close()
    page.close()


def test_vendor_choice_asks_the_backend(server, browser):
    page = browser.new_page()
    page.goto(server + "/demo")
    page.get_by_role("button", name="Campus A").click()
    page.get_by_role("button", name="Business or vendor enquiry").click()
    page.get_by_text("scripted test reply").wait_for()
    page.close()
