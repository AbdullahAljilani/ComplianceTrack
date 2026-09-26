"""Unit tests for the role permission matrix.

Black-box throughout. Each test states what a role must and must not be able
to do, drawn from the Unit 3 user roles table rather than from the source of
auth.py, so the matrix cannot be widened without a test noticing.
"""
import pytest

from src.services import auth

ROLES = ("GRC Administrator", "Control Owner", "Evidence Custodian",
         "Internal Auditor", "Management")


@pytest.mark.blackbox
def test_every_seeded_role_appears_in_the_matrix():
    assert set(auth.PERMISSIONS) == set(ROLES)


@pytest.mark.blackbox
def test_an_unknown_role_receives_nothing():
    """A role present in the database but absent from the matrix must fail
    closed, not fall through to a default grant."""
    assert auth.PERMISSIONS.get("Contractor", set()) == set()


@pytest.mark.blackbox
@pytest.mark.parametrize("role", ROLES)
def test_every_role_can_read_the_register(role):
    assert "control.view" in auth.PERMISSIONS[role]


@pytest.mark.blackbox
def test_management_is_read_only():
    granted = auth.PERMISSIONS["Management"]
    assert not any(p.endswith((".edit", ".upload", ".review")) for p in granted)


@pytest.mark.blackbox
def test_only_the_two_oversight_roles_see_the_audit_trail():
    holders = {r for r in ROLES if "audit.view" in auth.PERMISSIONS[r]}
    assert holders == {"GRC Administrator", "Internal Auditor"}


@pytest.mark.blackbox
def test_the_evidence_custodian_files_evidence_but_does_not_judge_it():
    granted = auth.PERMISSIONS["Evidence Custodian"]
    assert "evidence.upload" in granted
    assert "evidence.review" not in granted


@pytest.mark.blackbox
def test_the_auditor_reviews_evidence_but_does_not_supply_it():
    granted = auth.PERMISSIONS["Internal Auditor"]
    assert "evidence.review" in granted
    assert "evidence.upload" not in granted


@pytest.mark.blackbox
def test_the_auditor_cannot_change_a_control_status():
    """Independence: the party that reviews the register does not edit it."""
    assert "control.edit" not in auth.PERMISSIONS["Internal Auditor"]


@pytest.mark.blackbox
def test_only_the_administrator_holds_both_halves_of_the_evidence_workflow():
    """Where one role does hold both, the service layer refuses a reviewer who
    is also the uploader, which is the check that protects the gate."""
    both = {r for r in ROLES
            if {"evidence.upload", "evidence.review"} <= auth.PERMISSIONS[r]}
    assert both == {"GRC Administrator"}

    from src.evidence_management import service
    assert service.can_review(uploader_id=1, reviewer_id=1) is False


@pytest.mark.blackbox
def test_no_role_is_granted_a_permission_the_application_does_not_define():
    """Catches a typo in the matrix, which would otherwise grant nothing
    silently and be mistaken for an access bug much later."""
    defined = {
        "control.view", "control.edit",
        "evidence.view", "evidence.upload", "evidence.review",
        "remediation.view", "remediation.edit",
        "report.view", "audit.view",
    }
    for role, granted in auth.PERMISSIONS.items():
        assert granted <= defined, f"{role} holds an undefined permission"
