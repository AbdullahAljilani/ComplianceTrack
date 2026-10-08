"""Unit tests for the Remediation Tracker.

The ordering and closure tests are black-box: they state the behaviour the
module promises without depending on how prioritise() builds its sort key. The
validation tests are white-box, one per guard clause.
"""
from datetime import timedelta

import pytest

from src.remediation_tracker import service


def item(rid, status="Open", priority="Medium", due=None, owner=2):
    return {"remediation_id": rid, "status": status, "priority": priority,
            "due_date": due, "owner_user_id": owner}


# ---------------------------------------------------------------------------
# Creation rules
# ---------------------------------------------------------------------------

@pytest.mark.whitebox
def test_a_well_formed_finding_is_accepted(today):
    ok, reason = service.validate_new_item(
        "Privileged access review has not been evidenced this cycle.",
        7, "High", today + timedelta(days=30), today)
    assert (ok, reason) == (True, None)


@pytest.mark.whitebox
def test_a_finding_must_be_described(today):
    ok, reason = service.validate_new_item("gap", 7, "High",
                                           today + timedelta(days=5), today)
    assert not ok and "10 characters" in reason


@pytest.mark.whitebox
def test_an_unknown_priority_is_refused(today):
    ok, reason = service.validate_new_item("A described finding here.", 7,
                                           "Urgent", today + timedelta(days=5), today)
    assert not ok and "not a valid priority" in reason


@pytest.mark.whitebox
def test_a_missing_due_date_is_refused(today):
    ok, reason = service.validate_new_item("A described finding here.", 7,
                                           "Low", None, today)
    assert not ok and "due date" in reason


@pytest.mark.whitebox
def test_a_due_date_in_the_past_is_refused(today):
    """An item that is overdue the moment it is raised says nothing about
    whether anyone is late, so the form refuses it."""
    ok, reason = service.validate_new_item("A described finding here.", 7,
                                           "Low", today - timedelta(days=1), today)
    assert not ok and "cannot be in the past" in reason


@pytest.mark.whitebox
def test_a_due_date_of_today_is_allowed(today):
    ok, _ = service.validate_new_item("A described finding here.", 7, "Low",
                                      today, today)
    assert ok


# ---------------------------------------------------------------------------
# Closure rules. Unit 5 let the owner close an item outright; Unit 6 splits
# closure into a request by the owner and a verification by someone else (FR-7).
# The five Unit 5 tests carry over to the request step unchanged in intent.
# ---------------------------------------------------------------------------

def pending(rid=1, owner=7, requested_by=7):
    row = item(rid, status="Pending Verification", owner=owner)
    row["closure_requested_by"] = requested_by
    return row


@pytest.mark.blackbox
def test_the_owner_may_request_closure_of_their_own_item():
    ok, _ = service.can_request_closure(item(1, owner=7), actor_id=7,
                                        actor_role="Control Owner",
                                        note="Access review completed and signed off.")
    assert ok


@pytest.mark.blackbox
def test_an_administrator_may_request_closure_for_someone_else():
    """Someone has to be able to finish an item whose owner has left."""
    ok, _ = service.can_request_closure(item(1, owner=7), actor_id=1,
                                        actor_role="GRC Administrator",
                                        note="Closed after handover from the former owner.")
    assert ok


@pytest.mark.blackbox
def test_an_unrelated_user_may_not_request_closure():
    ok, reason = service.can_request_closure(item(1, owner=7), actor_id=9,
                                             actor_role="Internal Auditor",
                                             note="Looks finished to me, closing.")
    assert not ok and "owner" in reason


@pytest.mark.blackbox
def test_a_closure_request_requires_a_note():
    ok, reason = service.can_request_closure(item(1, owner=7), actor_id=7,
                                             actor_role="Control Owner", note="done")
    assert not ok and "10 characters" in reason


@pytest.mark.blackbox
def test_an_already_closed_item_cannot_be_requested_again():
    ok, reason = service.can_request_closure(item(1, status="Closed", owner=7),
                                             actor_id=7, actor_role="Control Owner",
                                             note="Trying to close it a second time.")
    assert not ok and "already closed" in reason


@pytest.mark.blackbox
def test_a_pending_request_is_not_requested_twice():
    ok, reason = service.can_request_closure(pending(), actor_id=7,
                                             actor_role="Control Owner",
                                             note="Submitting the same claim again.")
    assert not ok and "awaiting verification" in reason


@pytest.mark.blackbox
def test_someone_independent_may_verify_a_closure():
    ok, _ = service.can_verify_closure(pending(owner=7, requested_by=7),
                                       actor_id=5, decision="approve", note="")
    assert ok


@pytest.mark.blackbox
def test_the_owner_may_not_verify_their_own_closure():
    """FR-7, the rule Unit 6 adds."""
    ok, reason = service.can_verify_closure(pending(owner=7, requested_by=7),
                                            actor_id=7, decision="approve", note="")
    assert not ok and "someone other than" in reason


@pytest.mark.blackbox
def test_the_requester_may_not_verify_the_request_they_made():
    """An administrator who asked for closure on an owner's behalf is not
    independent of that claim either."""
    ok, _ = service.can_verify_closure(pending(owner=7, requested_by=1),
                                       actor_id=1, decision="approve", note="")
    assert not ok


@pytest.mark.blackbox
def test_only_an_item_awaiting_verification_can_be_verified():
    ok, reason = service.can_verify_closure(item(1, status="In Progress", owner=7),
                                            actor_id=5, decision="approve", note="")
    assert not ok and "not awaiting verification" in reason


@pytest.mark.whitebox
def test_returning_a_claim_needs_a_reason_and_unknown_decisions_are_refused():
    ok, reason = service.can_verify_closure(pending(), actor_id=5,
                                            decision="return", note="no")
    assert not ok and "10 characters" in reason
    ok, reason = service.can_verify_closure(pending(), actor_id=5,
                                            decision="maybe", note="")
    assert not ok and "not a valid" in reason
    ok, _ = service.can_verify_closure(pending(), actor_id=5, decision="return",
                                       note="The sign-off sheet is not attached.")
    assert ok


@pytest.mark.blackbox
def test_the_owner_starts_work_on_their_own_open_item():
    ok, _ = service.can_advance(item(1, owner=7), 7, "Control Owner", "In Progress")
    assert ok


@pytest.mark.blackbox
def test_someone_else_cannot_move_an_owners_item():
    ok, reason = service.can_advance(item(1, owner=7), 9, "Internal Auditor",
                                     "In Progress")
    assert not ok and "owner" in reason


@pytest.mark.whitebox
@pytest.mark.parametrize("status", ["Pending Verification", "Closed"])
def test_an_item_past_the_owners_stage_is_not_moved_by_hand(status):
    ok, _ = service.can_advance(item(1, status=status, owner=7), 7,
                                "Control Owner", "In Progress")
    assert not ok


@pytest.mark.whitebox
def test_advance_refuses_closing_and_a_no_op():
    assert not service.can_advance(item(1, owner=7), 7, "Control Owner", "Closed")[0]
    assert not service.can_advance(item(1, status="In Progress", owner=7), 7,
                                   "Control Owner", "In Progress")[0]


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------

@pytest.mark.blackbox
def test_overdue_work_is_listed_before_work_that_is_merely_urgent(today):
    """A Low finding that slipped yesterday still outranks a Critical one due
    next month, because the first is already late."""
    overdue_low = item(1, priority="Low", due=today - timedelta(days=1))
    future_critical = item(2, priority="Critical", due=today + timedelta(days=30))
    order = service.prioritise([future_critical, overdue_low], today)
    assert [i["remediation_id"] for i in order] == [1, 2]


@pytest.mark.blackbox
def test_within_the_same_state_higher_priority_comes_first(today):
    low = item(1, priority="Low", due=today - timedelta(days=5))
    critical = item(2, priority="Critical", due=today - timedelta(days=5))
    order = service.prioritise([low, critical], today)
    assert [i["remediation_id"] for i in order] == [2, 1]


@pytest.mark.blackbox
def test_within_the_same_priority_the_earlier_due_date_comes_first(today):
    later = item(1, priority="High", due=today + timedelta(days=20))
    sooner = item(2, priority="High", due=today + timedelta(days=16))
    order = service.prioritise([later, sooner], today)
    assert [i["remediation_id"] for i in order] == [2, 1]


@pytest.mark.blackbox
def test_closed_items_sink_to_the_bottom(today):
    closed = item(1, status="Closed", priority="Critical",
                  due=today - timedelta(days=90))
    open_low = item(2, priority="Low", due=today + timedelta(days=60))
    order = service.prioritise([closed, open_low], today)
    assert [i["remediation_id"] for i in order] == [2, 1]


@pytest.mark.blackbox
def test_an_item_with_no_due_date_does_not_break_the_ordering(today):
    order = service.prioritise(
        [item(1, due=None), item(2, due=today - timedelta(days=2))], today)
    assert [i["remediation_id"] for i in order] == [2, 1]


# ---------------------------------------------------------------------------
# Display annotation
# ---------------------------------------------------------------------------

@pytest.mark.whitebox
def test_annotation_adds_the_derived_state_without_touching_the_source(today):
    source = item(1, due=today - timedelta(days=3))
    annotated = service.annotate([source], today)
    assert annotated[0]["derived_state"] == "overdue"
    assert annotated[0]["derived_days"] == 3
    assert "derived_state" not in source          # the caller's row is not mutated


@pytest.mark.whitebox
def test_a_closed_item_is_never_annotated_as_overdue(today):
    closed = item(1, status="Closed", due=today - timedelta(days=200))
    assert service.annotate([closed], today)[0]["derived_state"] == "closed"


@pytest.mark.whitebox
def test_a_finding_with_no_owner_is_refused(today):
    """Regression. The browser marks the owner field required, but a request
    built by hand omits it, and the missing value used to reach the database
    as an unhandled not-null violation."""
    ok, reason = service.validate_new_item("A described finding here.", None,
                                           "High", today + timedelta(days=7), today)
    assert not ok and "owner" in reason.lower()


# ---------------------------------------------------------------------------
# Paging (Unit 6, after the scale evaluation)
# ---------------------------------------------------------------------------

@pytest.mark.whitebox
def test_paging_returns_the_requested_slice_and_page_count():
    shown, page, pages = service.paginate(list(range(60)), 2, size=25)
    assert shown == list(range(25, 50)) and (page, pages) == (2, 3)


@pytest.mark.whitebox
@pytest.mark.parametrize("asked, expected", [(0, 1), (-4, 1), (99, 3), ("x", 1), (None, 1)])
def test_an_out_of_range_or_malformed_page_is_clamped(asked, expected):
    _, page, _ = service.paginate(list(range(60)), asked, size=25)
    assert page == expected


@pytest.mark.whitebox
def test_an_empty_list_is_one_empty_page():
    assert service.paginate([], 1) == ([], 1, 1)


@pytest.mark.blackbox
def test_an_item_awaiting_verification_is_still_ranked_as_open_work(today):
    """A claim is not a closure. Until someone verifies it, an overdue item
    keeps its place at the top of the list."""
    claimed = item(1, status="Pending Verification", priority="High",
                   due=today - timedelta(days=4))
    later = item(2, priority="Critical", due=today + timedelta(days=30))
    order = service.prioritise([later, claimed], today)
    assert [i["remediation_id"] for i in order] == [1, 2]
    assert service.annotate([claimed], today)[0]["derived_state"] == "overdue"
