"""Integration checks against a live PostgreSQL database.

Kept apart from the unit tests and marked 'integration' because they are not
unit tests: each one exercises the service layer, the data layer and the
database constraints together. They are here because some of the rules this
project depends on are enforced by the database rather than by Python, and a
test that stubs the database cannot see those at all.

    python -m pytest tests/test_integration_db.py -m integration

Each test runs inside a transaction that is rolled back afterwards, so the
suite can be run repeatedly against the same database without changing it.
"""
from datetime import date, timedelta

import pytest

from app import create_app
from src import db
from src.evidence_management import service as evidence
from src.remediation_tracker import service as remediation

pytestmark = pytest.mark.integration


@pytest.fixture
def ctx(tmp_path):
    """An application context whose transaction is rolled back after the test."""
    app = create_app()
    app.config["EVIDENCE_ROOT"] = str(tmp_path)
    with app.app_context():
        with app.test_request_context():
            yield app
            db.get_conn().rollback()


def _user(username):
    return db.query_one("SELECT user_id FROM users WHERE username = %s",
                        (username,))["user_id"]


def _control(ecc):
    return db.query_one("SELECT control_id, status FROM controls "
                        "WHERE ecc_reference = %s", (ecc,))


# ---------------------------------------------------------------------------
# Evidence workflow
# ---------------------------------------------------------------------------

def test_an_upload_is_versioned_hashed_and_left_pending(ctx):
    control = _control("2-1-3")
    uploader = _user("Custodian01")

    eid, reason = evidence.store_evidence(
        control["control_id"], uploader, "procedure.pdf", b"first revision",
        "Integration check", evidence.evidence_root(ctx.config))

    assert reason is None
    row = db.query_one("SELECT * FROM evidence WHERE evidence_id = %s", (eid,))
    assert row["version_no"] == 1
    assert row["status"] == evidence.PENDING
    assert row["sha256_hash"] == evidence.sha256_of(b"first revision")
    assert row["reviewed_by"] is None


def test_a_changed_document_becomes_the_next_version(ctx):
    control = _control("2-1-3")
    uploader = _user("Custodian01")
    root = evidence.evidence_root(ctx.config)

    evidence.store_evidence(control["control_id"], uploader, "procedure.pdf",
                            b"first revision", "", root)
    second, reason = evidence.store_evidence(
        control["control_id"], uploader, "procedure.pdf", b"second revision",
        "", root)

    assert reason is None
    assert db.query_one("SELECT version_no FROM evidence WHERE evidence_id = %s",
                        (second,))["version_no"] == 2


def test_the_identical_file_twice_is_refused_before_it_reaches_the_database(ctx):
    control = _control("2-1-3")
    uploader = _user("Custodian01")
    root = evidence.evidence_root(ctx.config)

    evidence.store_evidence(control["control_id"], uploader, "procedure.pdf",
                            b"same bytes", "", root)
    eid, reason = evidence.store_evidence(control["control_id"], uploader,
                                          "renamed.pdf", b"same bytes", "", root)

    assert eid is None
    assert "already filed" in reason


def test_the_uploader_cannot_approve_their_own_evidence(ctx):
    control = _control("2-1-3")
    uploader = _user("Custodian01")
    eid, _ = evidence.store_evidence(control["control_id"], uploader,
                                     "procedure.pdf", b"content", "",
                                     evidence.evidence_root(ctx.config))

    ok, message = evidence.review_evidence(eid, uploader, "approve", "Fine.")

    assert not ok
    assert "other than the person who uploaded" in message


def test_an_approval_records_who_made_it(ctx):
    control = _control("2-1-3")
    eid, _ = evidence.store_evidence(control["control_id"], _user("Custodian01"),
                                     "procedure.pdf", b"content", "",
                                     evidence.evidence_root(ctx.config))
    reviewer = _user("Auditor01")

    ok, _ = evidence.review_evidence(eid, reviewer, "approve", "Accepted.")

    row = db.query_one("SELECT status, reviewed_by, reviewed_at FROM evidence "
                       "WHERE evidence_id = %s", (eid,))
    assert ok
    assert row["status"] == evidence.APPROVED
    assert row["reviewed_by"] == reviewer
    assert row["reviewed_at"] is not None


def test_a_rejection_must_carry_a_reason(ctx):
    control = _control("2-1-3")
    eid, _ = evidence.store_evidence(control["control_id"], _user("Custodian01"),
                                     "procedure.pdf", b"content", "",
                                     evidence.evidence_root(ctx.config))

    ok, message = evidence.review_evidence(eid, _user("Auditor01"), "reject", "no")

    assert not ok and "at least 10 characters" in message


def test_the_same_record_cannot_be_reviewed_twice(ctx):
    control = _control("2-1-3")
    eid, _ = evidence.store_evidence(control["control_id"], _user("Custodian01"),
                                     "procedure.pdf", b"content", "",
                                     evidence.evidence_root(ctx.config))
    evidence.review_evidence(eid, _user("Auditor01"), "approve", "Accepted.")

    ok, message = evidence.review_evidence(eid, _user("Abdullah.Aljilani"),
                                           "reject", "Changed my mind about it.")

    assert not ok and "already been approved" in message


def test_rejecting_the_last_approved_record_demotes_an_implemented_control(ctx):
    """The condition that justified the status no longer holds, so the register
    must stop asserting it."""
    control = _control("2-1-3")
    root = evidence.evidence_root(ctx.config)
    eid, _ = evidence.store_evidence(control["control_id"], _user("Custodian01"),
                                     "procedure.pdf", b"content", "", root)
    evidence.review_evidence(eid, _user("Auditor01"), "approve", "Accepted.")
    db.execute("UPDATE controls SET status = 'Implemented' WHERE control_id = %s",
               (control["control_id"],))

    second, _ = evidence.store_evidence(control["control_id"], _user("Custodian01"),
                                        "procedure.pdf", b"other content", "", root)
    db.execute("UPDATE evidence SET status = 'Rejected', reviewed_by = %s, "
               "reviewed_at = now() WHERE evidence_id = %s",
               (_user("Auditor01"), eid))

    ok, message = evidence.review_evidence(second, _user("Auditor01"), "reject",
                                           "Draft document, not approved.")

    assert ok
    assert "Evidence Missing" in message
    assert db.query_one("SELECT status FROM controls WHERE control_id = %s",
                        (control["control_id"],))["status"] == "Evidence Missing"


def test_the_database_refuses_an_approval_with_no_named_reviewer(ctx):
    """Enforced by a CHECK constraint, so it holds even against a direct
    database change that bypasses the application."""
    import psycopg2
    control = _control("2-1-3")
    eid, _ = evidence.store_evidence(control["control_id"], _user("Custodian01"),
                                     "procedure.pdf", b"content", "",
                                     evidence.evidence_root(ctx.config))
    with pytest.raises(psycopg2.errors.CheckViolation):
        db.execute("UPDATE evidence SET status = 'Approved' WHERE evidence_id = %s",
                   (eid,))


# ---------------------------------------------------------------------------
# The evidence gate on the Control Register
# ---------------------------------------------------------------------------

def test_the_register_holds_no_implemented_control_without_approved_evidence(ctx):
    """The invariant the whole score depends on, stated over the live data."""
    assert evidence.find_gate_violations() == []


def test_reconciliation_moves_a_violating_control_and_logs_it(ctx):
    control = _control("2-1-3")
    db.execute("UPDATE controls SET status = 'Implemented' WHERE control_id = %s",
               (control["control_id"],))
    assert len(evidence.find_gate_violations()) == 1

    changed = evidence.reconcile_evidence_gate(actor_id=_user("Abdullah.Aljilani"))

    assert len(changed) == 1
    assert evidence.find_gate_violations() == []
    logged = db.query_one(
        "SELECT details FROM audit_log WHERE entity_type = 'control' "
        "AND entity_id = %s ORDER BY audit_id DESC LIMIT 1",
        (control["control_id"],))
    assert logged["details"]["reason"] == "evidence gate reconciliation"


# ---------------------------------------------------------------------------
# Remediation workflow
# ---------------------------------------------------------------------------

def test_a_finding_cannot_be_raised_against_a_catalogue_entry(ctx):
    catalogue = db.query_one("SELECT control_id FROM controls "
                             "WHERE scope_tier = 'catalog_only' LIMIT 1")
    rid, reason = remediation.create_item(
        catalogue["control_id"], "A described finding for the test.",
        _user("ControlOwner01"), "High", date.today() + timedelta(days=10),
        _user("Auditor01"))

    assert rid is None
    assert "not assessed" in reason


def test_a_raised_finding_is_open_and_appears_against_its_control(ctx):
    control = _control("2-1-3")
    rid, reason = remediation.create_item(
        control["control_id"], "Inventory omits hosts commissioned this quarter.",
        _user("ControlOwner01"), "High", date.today() + timedelta(days=21),
        _user("Auditor01"))

    assert reason is None
    items = remediation.list_for_control(control["control_id"])
    assert any(i["remediation_id"] == rid and i["status"] == "Open" for i in items)


def test_closing_an_item_records_the_closer_and_the_note(ctx):
    control = _control("2-1-3")
    rid, _ = remediation.create_item(
        control["control_id"], "A described finding for the test.",
        _user("ControlOwner01"), "Medium", date.today() + timedelta(days=14),
        _user("Auditor01"))
    owner = _user("ControlOwner01")

    ok, _ = remediation.close_item(rid, owner, "Control Owner",
                                   "Inventory rebuilt and reconciled against the CMDB.")

    row = db.query_one("SELECT status, closed_by, closure_note FROM "
                       "remediation_items WHERE remediation_id = %s", (rid,))
    assert ok
    assert row["status"] == "Closed"
    assert row["closed_by"] == owner
    assert row["closure_note"].startswith("Inventory rebuilt")


def test_the_database_refuses_a_closure_with_no_note(ctx):
    import psycopg2
    control = _control("2-1-3")
    rid, _ = remediation.create_item(
        control["control_id"], "A described finding for the test.",
        _user("ControlOwner01"), "Low", date.today() + timedelta(days=30),
        _user("Auditor01"))
    with pytest.raises(psycopg2.errors.CheckViolation):
        db.execute("UPDATE remediation_items SET status = 'Closed' "
                   "WHERE remediation_id = %s", (rid,))


def test_an_overdue_item_is_derived_not_stored(ctx):
    """Nothing writes an overdue flag. Moving the due date into the past is
    enough for the view to report it."""
    control = _control("2-1-3")
    rid, _ = remediation.create_item(
        control["control_id"], "A described finding for the test.",
        _user("ControlOwner01"), "Critical", date.today() + timedelta(days=5),
        _user("Auditor01"))
    assert not db.query("SELECT 1 FROM v_overdue_remediation WHERE remediation_id = %s",
                        (rid,))

    db.execute("UPDATE remediation_items SET due_date = %s WHERE remediation_id = %s",
               (date.today() - timedelta(days=2), rid))

    row = db.query_one("SELECT days_overdue FROM v_overdue_remediation "
                       "WHERE remediation_id = %s", (rid,))
    assert row["days_overdue"] == 2


# ---------------------------------------------------------------------------
# Scoring over live data
# ---------------------------------------------------------------------------

def test_the_dashboard_summary_is_internally_consistent(ctx):
    from src.services import scoring
    summary = scoring.dashboard_summary()

    tracked = db.query_one("SELECT COUNT(*) AS n FROM controls "
                           "WHERE scope_tier = 'in_scope'")["n"]
    assert summary["implementation"]["assessed"] + \
           summary["implementation"]["excluded"] == tracked
    assert 0 <= summary["implementation"]["score"] <= 100
    assert summary["evidence"]["evidenced"] <= summary["evidence"]["assessed"]
    assert summary["remediation"]["overdue"] <= summary["remediation"]["open"]


def test_the_scope_matches_the_project_charter(ctx):
    """68 of the 108 main controls are tracked; the remaining 40 are catalogue
    entries. The register must keep saying so."""
    rows = {r["scope_tier"]: r["n"] for r in db.query(
        "SELECT scope_tier, COUNT(*) AS n FROM controls GROUP BY scope_tier")}
    assert rows == {"in_scope": 68, "catalog_only": 40}


def test_a_search_term_containing_sql_is_treated_as_data(ctx):
    """The register is still standing after a term that would end the statement
    if it were being concatenated in."""
    rows = db.query(
        "SELECT control_id FROM controls WHERE description ILIKE %s",
        ("%' OR 1=1; DROP TABLE controls; --%",))
    assert rows == []
    assert db.query_one("SELECT COUNT(*) AS n FROM controls")["n"] == 108
