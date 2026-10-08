"""End-to-end checks through the HTTP layer, using Flask's test client.

Marked integration for the same reason as test_integration_db.py: these
exercise routing, templates, authorisation, the services and the database at
once. They are here because a rule that holds in the service layer is only
actually enforced if the route applies it, and because a template error is
invisible to every test that never renders the page.
"""
import io
import re

import pytest

from app import create_app
from src import db

pytestmark = pytest.mark.integration

PASSWORD = "ChangeMe#2026"


@pytest.fixture
def client(tmp_path):
    app = create_app()
    app.config.update(TESTING=True, EVIDENCE_ROOT=str(tmp_path))
    with app.test_client() as c:
        yield c


def csrf(client, path):
    html = client.get(path).get_data(as_text=True)
    found = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return found.group(1) if found else None


def sign_in(client, username):
    token = csrf(client, "/login")
    return client.post("/login", data={"username": username,
                                       "password": PASSWORD,
                                       "csrf_token": token})


def control_id(ecc):
    app = create_app()
    with app.app_context():
        return db.query_one("SELECT control_id FROM controls WHERE ecc_reference = %s",
                            (ecc,))["control_id"]


# ---------------------------------------------------------------------------
# Every new page renders
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/", "/controls/", "/remediation/",
                                  "/remediation/new"])
def test_pages_render_for_the_administrator(client, path):
    sign_in(client, "Abdullah.Aljilani")
    response = client.get(path)
    assert response.status_code == 200


def test_the_evidence_page_renders(client):
    sign_in(client, "Abdullah.Aljilani")
    response = client.get(f"/evidence/control/{control_id('1-1-1')}")
    assert response.status_code == 200
    assert b"Version history" in response.data


def test_the_dashboard_shows_the_scoring_indicators(client):
    sign_in(client, "Abdullah.Aljilani")
    body = client.get("/").get_data(as_text=True)
    assert "Weighted implementation score" in body
    assert "Evidence coverage" in body
    assert "Priority-weighted exposure" in body


def test_the_dashboard_still_states_the_no_certification_boundary(client):
    sign_in(client, "Manager01")
    body = client.get("/").get_data(as_text=True)
    assert "does not certify" in body


# ---------------------------------------------------------------------------
# Authorisation is enforced by the route, not only by the service
# ---------------------------------------------------------------------------

def test_a_read_only_role_is_refused_the_upload_route(client):
    sign_in(client, "Manager01")
    cid = control_id("1-1-1")
    response = client.post(f"/evidence/control/{cid}/upload",
                           data={"csrf_token": csrf(client, f"/evidence/control/{cid}"),
                                 "document": (io.BytesIO(b"x"), "a.pdf")},
                           content_type="multipart/form-data")
    assert response.status_code == 403


def test_the_custodian_is_refused_the_review_route(client):
    sign_in(client, "Custodian01")
    response = client.post("/evidence/1/review",
                           data={"decision": "approve", "control_id": 1,
                                 "csrf_token": csrf(client, "/controls/")})
    assert response.status_code == 403


def test_a_read_only_role_is_refused_the_remediation_form(client):
    sign_in(client, "Manager01")
    assert client.get("/remediation/new").status_code == 403


def test_an_anonymous_request_to_a_new_page_is_redirected_to_sign_in(client):
    response = client.get("/remediation/", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_an_upload_without_a_csrf_token_is_rejected(client):
    sign_in(client, "Custodian01")
    cid = control_id("1-1-1")
    response = client.post(f"/evidence/control/{cid}/upload",
                           data={"document": (io.BytesIO(b"x"), "a.pdf")},
                           content_type="multipart/form-data")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# The upload path end to end
# ---------------------------------------------------------------------------

def test_an_upload_of_a_refused_format_reports_why(client):
    sign_in(client, "Custodian01")
    cid = control_id("2-1-5")
    response = client.post(
        f"/evidence/control/{cid}/upload",
        data={"csrf_token": csrf(client, f"/evidence/control/{cid}"),
              "description": "Test",
              "document": (io.BytesIO(b"binary"), "payload.exe")},
        content_type="multipart/form-data", follow_redirects=True)
    assert b"not an accepted evidence format" in response.data


def test_an_upload_with_no_file_chosen_reports_why(client):
    sign_in(client, "Custodian01")
    cid = control_id("2-1-5")
    response = client.post(
        f"/evidence/control/{cid}/upload",
        data={"csrf_token": csrf(client, f"/evidence/control/{cid}")},
        content_type="multipart/form-data", follow_redirects=True)
    assert b"Choose a file to upload" in response.data


def test_a_file_above_the_hard_request_cap_does_not_return_a_raw_error(client):
    """Flask rejects a request over MAX_CONTENT_LENGTH before the view runs, so
    the friendly size message in the service never gets the chance to fire.
    The application must still answer with its own page rather than a bare
    werkzeug error."""
    sign_in(client, "Custodian01")
    cid = control_id("2-1-5")
    oversized = io.BytesIO(b"x" * (13 * 1024 * 1024))
    response = client.post(
        f"/evidence/control/{cid}/upload",
        data={"csrf_token": csrf(client, f"/evidence/control/{cid}"),
              "document": (oversized, "big.pdf")},
        content_type="multipart/form-data", follow_redirects=True)
    assert response.status_code in (200, 413)
    assert b"Request Entity Too Large" not in response.data


# ---------------------------------------------------------------------------
# The Implemented gate, through the interface
# ---------------------------------------------------------------------------

def test_the_register_refuses_implemented_without_approved_evidence(client):
    sign_in(client, "Abdullah.Aljilani")
    cid = control_id("2-1-5")
    response = client.post(f"/controls/{cid}/status",
                           data={"status": "Implemented",
                                 "csrf_token": csrf(client, f"/controls/{cid}")},
                           follow_redirects=True)
    assert b"cannot be marked Implemented" in response.data


def test_the_control_page_links_to_its_evidence(client):
    sign_in(client, "Abdullah.Aljilani")
    cid = control_id("1-1-1")
    body = client.get(f"/controls/{cid}").get_data(as_text=True)
    assert f"/evidence/control/{cid}" in body


# ---------------------------------------------------------------------------
# The remediation list
# ---------------------------------------------------------------------------

def test_the_tracker_marks_overdue_items(client):
    sign_in(client, "Abdullah.Aljilani")
    body = client.get("/remediation/").get_data(as_text=True)
    assert "Overdue by" in body


def test_raising_a_finding_with_a_past_due_date_is_refused(client):
    sign_in(client, "Abdullah.Aljilani")
    response = client.post("/remediation/new",
                           data={"csrf_token": csrf(client, "/remediation/new"),
                                 "control_id": control_id("2-1-5"),
                                 "finding": "A described finding for this test.",
                                 "owner_user_id": 2, "priority": "High",
                                 "due_date": "2020-01-01"})
    assert response.status_code == 400
    assert b"cannot be in the past" in response.data


def test_a_finding_submitted_with_no_owner_does_not_crash(client):
    """The owner field is required by the form, but a request that omits it
    reaches the service with owner_user_id as None. Client-side 'required' is
    presentation; the server has to refuse it."""
    sign_in(client, "Abdullah.Aljilani")
    response = client.post("/remediation/new",
                           data={"csrf_token": csrf(client, "/remediation/new"),
                                 "control_id": control_id("2-1-5"),
                                 "finding": "A described finding for this test.",
                                 "priority": "High",
                                 "due_date": "2027-01-15"})
    assert response.status_code == 400
    assert b"owner" in response.data.lower()


# ---------------------------------------------------------------------------
# Unit 6: sign-in lands every role somewhere it may be, and FR-1 ownership
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("username", ["Abdullah.Aljilani", "ControlOwner01",
                                      "ControlOwner02", "Custodian01",
                                      "Auditor01", "Manager01"])
def test_every_account_lands_on_a_page_it_may_see(client, username):
    response = sign_in(client, username)
    assert response.status_code == 302
    assert client.get(response.headers["Location"]).status_code == 200


def test_the_custodian_is_not_offered_the_dashboard(client):
    sign_in(client, "Custodian01")
    body = client.get("/controls/").get_data(as_text=True)
    assert ">Dashboard<" not in body


def test_the_sign_in_page_lists_the_accounts_that_exist(client):
    body = client.get("/login").get_data(as_text=True)
    assert "Abdullah.Aljilani" in body and "Custodian01" in body
    assert "a.rashid" not in body


def owner_of(ecc):
    app = create_app()
    with app.app_context():
        return db.query_one(
            "SELECT u.username FROM controls c JOIN users u "
            "ON u.user_id = c.owner_user_id WHERE c.ecc_reference = %s", (ecc,))["username"]


def status_of(ecc):
    app = create_app()
    with app.app_context():
        return db.query_one("SELECT status FROM controls WHERE ecc_reference = %s",
                            (ecc,))["status"]


def test_an_owner_is_refused_a_change_to_another_owners_control(client):
    """FR-1, through the route. Found by the Unit 6 integration review."""
    assert owner_of("1-4-1") == "ControlOwner02"
    before = status_of("1-4-1")
    sign_in(client, "ControlOwner01")
    cid = control_id("1-4-1")
    response = client.post(f"/controls/{cid}/status",
                           data={"status": "Partially Implemented",
                                 "csrf_token": csrf(client, f"/controls/{cid}")})
    assert response.status_code == 403
    assert status_of("1-4-1") == before


def test_the_assigned_owner_passes_the_ownership_check(client):
    """Submits the current status, so the request clears authorisation and the
    route answers 'unchanged' without writing anything."""
    owner = owner_of("1-4-1")
    sign_in(client, owner)
    cid = control_id("1-4-1")
    response = client.post(f"/controls/{cid}/status",
                           data={"status": status_of("1-4-1"),
                                 "csrf_token": csrf(client, f"/controls/{cid}")},
                           follow_redirects=True)
    assert response.status_code == 200
    assert b"Status unchanged" in response.data


def test_the_status_form_is_hidden_from_an_owner_who_does_not_own_the_control(client):
    sign_in(client, "ControlOwner01")
    body = client.get(f"/controls/{control_id('1-4-1')}").get_data(as_text=True)
    assert "/status" not in body
    assert "are made by its" in body


# ---------------------------------------------------------------------------
# Unit 6: closure needs a request and an independent verification (FR-7)
# ---------------------------------------------------------------------------

def open_item_owned_by(username):
    app = create_app()
    with app.app_context():
        return db.query_one(
            "SELECT r.remediation_id, r.status FROM remediation_items r "
            "JOIN users u ON u.user_id = r.owner_user_id "
            "WHERE u.username = %s AND r.status IN ('Open', 'In Progress') "
            "ORDER BY r.remediation_id LIMIT 1", (username,))


def item_status(rid):
    app = create_app()
    with app.app_context():
        return db.query_one("SELECT status FROM remediation_items "
                            "WHERE remediation_id = %s", (rid,))["status"]


def test_the_one_step_closure_route_is_gone(client):
    sign_in(client, "ControlOwner01")
    rid = open_item_owned_by("ControlOwner01")["remediation_id"]
    response = client.post(f"/remediation/{rid}/close",
                           data={"csrf_token": csrf(client, "/remediation/"),
                                 "note": "Trying the Unit 5 route directly."})
    assert response.status_code in (404, 405)
    assert item_status(rid) != "Closed"


def test_an_owner_is_refused_the_verification_route(client):
    sign_in(client, "ControlOwner01")
    rid = open_item_owned_by("ControlOwner01")["remediation_id"]
    response = client.post(f"/remediation/{rid}/verify",
                           data={"csrf_token": csrf(client, "/remediation/"),
                                 "decision": "approve"})
    assert response.status_code == 403


def test_someone_who_is_not_the_owner_cannot_request_closure(client):
    item = open_item_owned_by("ControlOwner02")
    sign_in(client, "Auditor01")
    response = client.post(f"/remediation/{item['remediation_id']}/request-closure",
                           data={"csrf_token": csrf(client, "/remediation/"),
                                 "note": "The auditor is not the owner of this item."},
                           follow_redirects=True)
    assert b"Only the assigned owner" in response.data
    assert item_status(item["remediation_id"]) == item["status"]


def test_the_tracker_shows_the_verification_queue_and_pages(client):
    sign_in(client, "Auditor01")
    body = client.get("/remediation/?page=1").get_data(as_text=True)
    assert "Awaiting verification" in body
    assert client.get("/remediation/?page=99").status_code == 200
    assert client.get("/remediation/?mine=1").status_code == 200


# ---------------------------------------------------------------------------
# Unit 6: exportable summaries and the JSON summary
# ---------------------------------------------------------------------------

def _csv_body(text):
    return [ln for ln in text.splitlines() if not ln.startswith("#")]


def test_management_can_export_the_domain_summary(client):
    sign_in(client, "Manager01")
    response = client.get("/reports/domain-summary.csv")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert response.headers["Cache-Control"] == "no-store"
    assert "attachment" in response.headers["Content-Disposition"]
    text = response.get_data(as_text=True)
    assert "does not certify" in text
    assert _csv_body(text)[-1].startswith("All tracked domains")


def test_the_control_extract_lists_every_tracked_control_once(client):
    sign_in(client, "Auditor01")
    text = client.get("/reports/controls.csv").get_data(as_text=True)
    import csv as _csv
    rows = list(_csv.DictReader(io.StringIO("\n".join(_csv_body(text)))))
    assert len(rows) == 68
    assert len({r["ECC reference"] for r in rows}) == 68


def test_a_role_without_report_access_cannot_export(client):
    sign_in(client, "Custodian01")
    assert client.get("/reports/controls.csv").status_code == 403
    assert client.get("/api/summary").status_code == 403


def test_an_export_is_recorded_in_the_audit_trail(client):
    sign_in(client, "Manager01")
    client.get("/reports/domain-summary.csv")
    app = create_app()
    with app.app_context():
        row = db.query_one(
            "SELECT a.action, a.details, u.username FROM audit_log a "
            "JOIN users u ON u.user_id = a.user_id "
            "ORDER BY a.audit_id DESC LIMIT 1")
    assert row["action"] == "REPORT_EXPORT"
    assert row["username"] == "Manager01"
    assert row["details"]["report"] == "domain-summary.csv"


def test_the_summary_api_returns_the_dashboard_figures(client):
    sign_in(client, "Abdullah.Aljilani")
    response = client.get("/api/summary")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    data = response.get_json()
    assert {"implementation", "evidence", "remediation", "by_domain",
            "domain_gaps", "boundary"} <= set(data)
    assert "does not certify" in data["boundary"]


def test_the_dashboard_shows_missing_evidence_and_overdue_by_domain(client):
    sign_in(client, "Abdullah.Aljilani")
    body = client.get("/").get_data(as_text=True)
    assert "Missing evidence" in body and "Overdue items" in body
    assert "/reports/domain-summary.csv" in body


def test_pages_are_never_stored_by_a_shared_cache_but_stylesheets_may_be(client):
    """Unit 6, with the Flask 3.1.3 upgrade (CVE-2026-27205)."""
    sign_in(client, "Manager01")
    assert client.get("/").headers["Cache-Control"] == "no-store"
    assert client.get("/login").headers["Cache-Control"] == "no-store"
    assert client.get("/static/css/app.css").headers.get("Cache-Control") != "no-store"


def test_the_overdue_tile_counts_the_whole_register_under_any_filter(client):
    """Unit 6 heuristic review: the tile used to show the filtered figure."""
    sign_in(client, "Abdullah.Aljilani")
    tile = re.compile(r'<div class="n">(\d+)</div><div class="l">Overdue</div>')
    unfiltered = tile.search(client.get("/remediation/").get_data(as_text=True)).group(1)
    closed_view = tile.search(
        client.get("/remediation/?status=Closed").get_data(as_text=True)).group(1)
    assert unfiltered == closed_view
