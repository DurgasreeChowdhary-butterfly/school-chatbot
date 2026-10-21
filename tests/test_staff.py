"""Staff page: login, rate limiting, data, status changes, CSV export."""
import csv
import io

from backend.app import db
from backend.app.staff import MAX_FAILED_LOGINS

HEADERS = {"X-Requested-With": "staff-page"}


def login(client, password="test-password"):
    return client.post("/staff/login", data={"password": password}, follow_redirects=False)


def add_enquiry(**extra):
    return db.insert("enquiries", {"campus": "pilot-campus", "parent_name": "Sample Parent", "child_name": "Sample Child",
                                   "class_applying": "Grade 3", "mobile": "9876543210", "visit_preference": "Saturday",
                                   "assigned_to": "Admission counsellor", **extra})


def test_staff_page_needs_login(client):
    page = client.get("/staff")
    assert page.status_code == 200 and 'name="password"' in page.text
    assert client.get("/staff/api/data").status_code == 401
    assert client.get("/staff/export/enquiries.csv").status_code == 401
    assert client.post("/staff/api/status", json={"kind": "tickets", "ref": "T-1", "status": "Resolved"},
                       headers=HEADERS).status_code == 401


def test_wrong_password(client):
    r = login(client, "nope")
    assert r.status_code == 401 and "Wrong password" in r.text
    assert client.get("/staff/api/data").status_code == 401


def test_login_and_see_data(client):
    add_enquiry()
    r = login(client)
    assert r.status_code == 303 and "staff_session" in r.cookies
    data = client.get("/staff/api/data").json()
    assert data["demo"] is True
    assert data["enquiries"][0]["ref"] == "E-1001"
    assert "Staff view" in client.get("/staff").text


def test_login_attempts_are_rate_limited(client):
    for _ in range(MAX_FAILED_LOGINS):
        assert login(client, "guess").status_code == 401
    blocked = login(client)  # even the right password is refused now
    assert blocked.status_code == 429 and "Too many" in blocked.text


def test_login_switched_off_without_password(client, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    assert login(client, "").status_code == 503
    assert "ADMIN_PASSWORD" in client.get("/staff").text


def test_logout(client):
    login(client)
    client.post("/staff/logout")
    assert client.get("/staff/api/data").status_code == 401


def test_change_status(client):
    add_enquiry()
    login(client)
    ok = client.post("/staff/api/status", json={"kind": "enquiries", "ref": "E-1001", "status": "Contacted"}, headers=HEADERS)
    assert ok.status_code == 200
    assert db.find_one("enquiries", ref="E-1001")["status"] == "Contacted"
    bad = client.post("/staff/api/status", json={"kind": "enquiries", "ref": "E-1001", "status": "Deleted"}, headers=HEADERS)
    assert bad.status_code == 400
    missing = client.post("/staff/api/status", json={"kind": "tickets", "ref": "T-9", "status": "Resolved"}, headers=HEADERS)
    assert missing.status_code == 404


def test_changes_need_the_staff_page_header(client):
    add_enquiry()
    login(client)
    r = client.post("/staff/api/status", json={"kind": "enquiries", "ref": "E-1001", "status": "Contacted"})
    assert r.status_code == 403
    assert db.find_one("enquiries", ref="E-1001")["status"] == "New"


def test_csv_export_is_safe_from_formulas(client):
    add_enquiry(reason="=HYPERLINK(\"http://evil\")")
    login(client)
    r = client.get("/staff/export/enquiries.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    [row] = list(csv.DictReader(io.StringIO(r.text)))
    assert row["ref"] == "E-1001" and row["reason"].startswith("'=")
    assert client.get("/staff/export/secrets.csv").status_code == 404


def test_run_reminders_from_staff_page(client):
    login(client)
    assert client.post("/staff/api/run-reminders", headers=HEADERS).json() == {"notifications": 0}
