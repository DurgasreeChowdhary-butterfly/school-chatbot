"""Security checks in a real (headless) browser: text typed by parents can never run as code on the staff page,
and the chat window's session id stays unguessable even where crypto.randomUUID is missing (plain-http sites)."""
import re

import pytest

pytest.importorskip("playwright.sync_api")

from tests.test_widget_browser import BROWSER_DB, browser, server  # noqa: E402,F401  (shared fixtures)

PAYLOADS = [
    '<script>window.__xss = "script"</script>',
    '<img src=x onerror="window.__xss = \'img\'">',
    '"><svg onload="window.__xss = \'svg\'">',
    "</td></tr><b id=injected>bold</b>",
]


def test_parent_text_never_runs_on_the_staff_page(server, browser):
    from backend.app import db
    from backend.app.notify import notify
    from backend.app.routing import role

    db.init_db(BROWSER_DB["path"])
    p = " ".join(PAYLOADS)
    db.insert("enquiries", {"campus": "pilot-campus", "parent_name": p, "child_name": p, "class_applying": "Grade 3",
                            "mobile": "9000000003", "visit_preference": p, "previous_school": p, "reason": p,
                            "notes": p, "assigned_to": "Admission counsellor"})
    t = db.insert("tickets", {"campus": "pilot-campus", "category": "Transport", "description": p, "parent_name": p,
                              "mobile": "9000000004", "urgent": 0, "first_contact": "Transport coordinator",
                              "backup_contact": "Principal"})
    db.insert("callbacks", {"campus": "pilot-campus", "name": p, "mobile": "9000000005", "reason": p,
                            "assigned_to": "Front office"})
    notify("pilot-campus", role("pilot-campus", "Principal"), f"Ticket {t['ref']} {p}", p, t["ref"], "ticket")

    page = browser.new_page(viewport={"width": 1280, "height": 900})
    blocked = []
    page.on("console", lambda m: blocked.append(m.text) if "Content Security Policy" in m.text else None)
    page.goto(server + "/staff")
    page.fill("input[name=password]", "browser-test")
    page.click("button[type=submit]")
    page.get_by_role("heading", name="Staff view").wait_for()
    page.wait_for_timeout(500)
    assert page.evaluate("window.__xss") is None                 # no payload ran
    assert page.locator("#injected").count() == 0                # no markup was created from parent text
    assert page.get_by_text('<script>window.__xss = "script"</script>').count() >= 1  # shown as plain text
    page.locator("details summary").first.click()                # the outbox body too
    page.wait_for_timeout(200)
    assert page.evaluate("window.__xss") is None
    page.close()


def test_staff_page_csp_blocks_injected_scripts(server, browser):
    """Even if a bug ever let markup through, the Content-Security-Policy stops scripts that are not ours."""
    page = browser.new_page()
    page.goto(server + "/staff")
    page.fill("input[name=password]", "browser-test")
    page.click("button[type=submit]")
    page.get_by_role("heading", name="Staff view").wait_for()
    page.evaluate("""() => { const s = document.createElement('script'); s.textContent = 'window.__csp = 1';
                             document.body.appendChild(s); }""")
    page.wait_for_timeout(200)
    assert page.evaluate("window.__csp") is None
    page.close()


def test_session_id_is_random_without_randomuuid(server, browser):
    page = browser.new_page()
    page.add_init_script("Object.defineProperty(crypto, 'randomUUID', { value: undefined });")
    page.goto(server + "/demo")
    page.locator(".sc-panel").wait_for(state="visible")
    ids = page.evaluate("Object.keys(sessionStorage).filter(k => k.endsWith('session')).map(k => sessionStorage[k])")
    assert len(ids) == 1
    sid = ids[0].strip('"')
    assert re.fullmatch(r"s-[0-9a-f]{32}", sid), sid   # 128 random bits from crypto.getRandomValues
    page.close()


def test_delete_a_persons_data_from_the_staff_page(server, browser):
    from backend.app import db

    db.init_db(BROWSER_DB["path"])
    db.insert("enquiries", {"campus": "pilot-campus", "parent_name": "Deleteme Parent", "child_name": "Sample Kid",
                            "class_applying": "Grade 3", "mobile": "9000000077", "visit_preference": "Saturday",
                            "assigned_to": "Admission counsellor"})
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(server + "/staff")
    page.fill("input[name=password]", "browser-test")
    page.click("button[type=submit]")
    page.get_by_role("heading", name="Staff view").wait_for()
    page.get_by_text("Deleteme Parent").wait_for()
    page.fill("#delMobile", "90000 00077")
    page.click("#delFind")
    page.get_by_text("Stored for this number: 1 enquiry.").wait_for()
    page.click("#delGo")                                   # without typing DELETE: refused
    page.get_by_text("Type DELETE (in capitals) to confirm.").wait_for()
    assert db.find_one("enquiries", mobile="9000000077") is not None
    page.fill("#delConfirm", "DELETE")
    page.click("#delGo")
    page.get_by_text("One person's data: 1 enquiry").wait_for()  # the audit log line
    assert db.find_one("enquiries", mobile="9000000077") is None
    assert page.get_by_text("Deleteme Parent").count() == 0
    page.close()
