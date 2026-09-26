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
        "High", today + timedelta(days=30), today)
    assert (ok, reason) == (True, None)


@pytest.mark.whitebox
def test_a_finding_must_be_described(today):
    ok, reason = service.validate_new_item("gap", "High",
                                           today + timedelta(days=5), today)
    assert not ok and "10 characters" in reason


@pytest.mark.whitebox
def test_an_unknown_priority_is_refused(today):
    ok, reason = service.validate_new_item("A described finding here.",
                                           "Urgent", today + timedelta(days=5), today)
    assert not ok and "not a valid priority" in reason


@pytest.mark.whitebox
def test_a_missing_due_date_is_refused(today):
    ok, reason = service.validate_new_item("A described finding here.",
                                           "Low", None, today)
    assert not ok and "due date" in reason


@pytest.mark.whitebox
def test_a_due_date_in_the_past_is_refused(today):
    """An item that is overdue the moment it is raised says nothing about
    whether anyone is late, so the form refuses it."""
    ok, reason = service.validate_new_item("A described finding here.",
                                           "Low", today - timedelta(days=1), today)
    assert not ok and "cannot be in the past" in reason


@pytest.mark.whitebox
def test_a_due_date_of_today_is_allowed(today):
    ok, _ = service.validate_new_item("A described finding here.", "Low",
                                      today, today)
    assert ok


# ---------------------------------------------------------------------------
# Closure rules
# ---------------------------------------------------------------------------

@pytest.mark.blackbox
def test_the_owner_may_close_their_own_item():
    ok, _ = service.can_close(item(1, owner=7), actor_id=7,
                              actor_role="Control Owner",
                              note="Access review completed and signed off.")
    assert ok


@pytest.mark.blackbox
def test_an_administrator_may_close_someone_elses_item():
    """Someone has to be able to close an item whose owner has left."""
    ok, _ = service.can_close(item(1, owner=7), actor_id=1,
                              actor_role="GRC Administrator",
                              note="Closed after handover from the former owner.")
    assert ok


@pytest.mark.blackbox
def test_an_unrelated_user_may_not_close_an_item():
    ok, reason = service.can_close(item(1, owner=7), actor_id=9,
                                   actor_role="Internal Auditor",
                                   note="Looks fine to me now.")
    assert not ok and "assigned owner or a GRC Administrator" in reason


@pytest.mark.blackbox
def test_closure_requires_a_note():
    ok, reason = service.can_close(item(1, owner=7), actor_id=7,
                                   actor_role="Control Owner", note="done")
    assert not ok and "10 characters" in reason


@pytest.mark.blackbox
def test_an_already_closed_item_cannot_be_closed_again():
    ok, reason = service.can_close(item(1, status="Closed", owner=7), actor_id=7,
                                   actor_role="Control Owner",
                                   note="Closing this a second time.")
    assert not ok and "already closed" in reason


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

