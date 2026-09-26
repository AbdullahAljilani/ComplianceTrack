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
