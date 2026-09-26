"""Unit tests for Evidence Management.

A mix of the two approaches the unit asks about. The validation and versioning
tests are white-box: they were written from the source to reach each branch of
validate_upload and next_version. The secure file handling tests are black-box:
they state what the module must refuse without reference to how the refusal is
implemented, so a later rewrite of sanitize_label has to keep satisfying them.
"""
import hashlib

import pytest

from src.evidence_management import service


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

@pytest.mark.whitebox
def test_digest_matches_the_reference_implementation():
    data = b"ComplianceTrack evidence"
    assert service.sha256_of(data) == hashlib.sha256(data).hexdigest()


@pytest.mark.whitebox
def test_one_changed_byte_changes_the_digest():
    assert service.sha256_of(b"policy v1") != service.sha256_of(b"policy v2")


# ---------------------------------------------------------------------------
# Secure file handling. Black-box: these state what must be refused.
# ---------------------------------------------------------------------------

@pytest.mark.blackbox
@pytest.mark.parametrize("hostile", [
    "../../etc/passwd",
    "../../../root/.ssh/id_rsa",
    "..\\..\\Windows\\System32\\config\\SAM",
    "/absolute/path/policy.pdf",
    "evidence/../../secret.pdf",
])
def test_no_directory_component_survives_sanitising(hostile):
    cleaned = service.sanitize_label(hostile)
    assert "/" not in cleaned
    assert "\\" not in cleaned
    assert not cleaned.startswith(".")


@pytest.mark.blackbox
def test_a_name_made_only_of_dots_still_produces_a_usable_label():
    assert service.sanitize_label("...") == "unnamed"
    assert service.sanitize_label("") == "unnamed"
    assert service.sanitize_label(None) == "unnamed"


@pytest.mark.blackbox
def test_stored_name_is_built_from_values_the_module_controls():
    name = service.stored_filename(7, 3, "../../etc/passwd")
    assert name.startswith("c0007_v003_")
    assert "/" not in name and ".." not in name


@pytest.mark.blackbox
def test_stored_names_of_two_versions_do_not_collide():
    first = service.stored_filename(7, 1, "policy.pdf")
    second = service.stored_filename(7, 2, "policy.pdf")
    assert first != second


# ---------------------------------------------------------------------------
# Upload validation. White-box: one test per branch, in the order checked.
# ---------------------------------------------------------------------------

@pytest.mark.whitebox
def test_an_accepted_document_passes():
    assert service.validate_upload("policy.pdf", b"x" * 100) == (True, None)


@pytest.mark.whitebox
def test_an_empty_file_is_refused():
    ok, reason = service.validate_upload("policy.pdf", b"")
    assert not ok and "empty" in reason.lower()


@pytest.mark.whitebox
def test_a_file_over_the_size_cap_is_refused():
    oversized = b"x" * (service.MAX_UPLOAD_BYTES + 1)
    ok, reason = service.validate_upload("policy.pdf", oversized)
    assert not ok and "larger" in reason.lower()


@pytest.mark.whitebox
def test_a_file_exactly_on_the_size_cap_is_accepted():
    """Boundary value. The cap is documented as a maximum, not a limit the
    file must stay below."""
    ok, _ = service.validate_upload("policy.pdf", b"x" * service.MAX_UPLOAD_BYTES)
    assert ok


@pytest.mark.blackbox
@pytest.mark.parametrize("filename", [
    "payload.exe", "script.sh", "macro.docm", "archive.zip", "noextension",
])
def test_formats_outside_the_allowlist_are_refused(filename):
    ok, reason = service.validate_upload(filename, b"content")
    assert not ok and "not an accepted evidence format" in reason


@pytest.mark.blackbox
def test_a_double_extension_is_judged_on_the_last_one():
    ok, _ = service.validate_upload("report.pdf.exe", b"content")
    assert not ok


@pytest.mark.blackbox
def test_extension_matching_ignores_case():
    ok, _ = service.validate_upload("REPORT.PDF", b"content")
    assert ok


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------

@pytest.mark.whitebox
def test_first_upload_is_version_one():
    assert service.next_version([]) == 1


@pytest.mark.whitebox
def test_next_version_continues_from_the_highest_used():
    assert service.next_version([1, 2, 3]) == 4


@pytest.mark.whitebox
def test_a_gap_in_the_chain_does_not_reuse_a_number():
    """A deleted version must not have its number handed out again, because the
    audit trail already refers to it."""
    assert service.next_version([1, 2, 5]) == 6


@pytest.mark.whitebox
def test_unordered_and_empty_input_is_handled():
    assert service.next_version([3, 1, 2]) == 4
    assert service.next_version([None]) == 1


@pytest.mark.whitebox
def test_the_same_file_twice_is_recognised_as_a_duplicate():
    digest = service.sha256_of(b"identical")
    assert service.is_duplicate(digest, [digest, "other"])
    assert not service.is_duplicate(service.sha256_of(b"changed"), [digest])


# ---------------------------------------------------------------------------
# Separation of duties
# ---------------------------------------------------------------------------

@pytest.mark.blackbox
def test_nobody_may_approve_their_own_evidence():
    assert service.can_review(uploader_id=4, reviewer_id=4) is False


@pytest.mark.blackbox
def test_a_different_reviewer_may_approve():
    assert service.can_review(uploader_id=4, reviewer_id=5) is True


@pytest.mark.whitebox
def test_review_decisions_are_mapped_and_anything_else_refused():
    assert service.resolve_review("approve") == service.APPROVED
    assert service.resolve_review("REJECT") == service.REJECTED
    assert service.resolve_review("maybe") is None
    assert service.resolve_review("") is None
