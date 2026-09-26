"""Unit tests for the compliance scoring service.

White-box tests. They were written against the source of scoring.py with the
aim of reaching every branch of the calculation, including the guard clauses
that should never fire in normal use.
"""
import pytest

from src.services import scoring


# ---------------------------------------------------------------------------
# weighted_implementation_score
# ---------------------------------------------------------------------------

@pytest.mark.whitebox
def test_all_implemented_scores_one_hundred():
    result = scoring.weighted_implementation_score({"Implemented": 10})
    assert result["score"] == 100.0
    assert result["assessed"] == 10


@pytest.mark.whitebox
def test_all_not_implemented_scores_zero():
    assert scoring.weighted_implementation_score({"Not Implemented": 8})["score"] == 0.0


@pytest.mark.whitebox
def test_partial_statuses_earn_their_documented_weight():
    # 4 x 1.00 + 4 x 0.50 + 4 x 0.25 + 4 x 0.00 = 7.0 over 16 assessed = 43.75
    counts = {"Implemented": 4, "Partially Implemented": 4,
              "Evidence Missing": 4, "Not Implemented": 4}
    result = scoring.weighted_implementation_score(counts)
    assert result["weighted_total"] == 7.0
    assert result["score"] == 43.8               # rounded to one decimal place


@pytest.mark.whitebox
def test_not_applicable_is_excluded_from_both_sides():
    """Scoping a control out must not move the score in either direction."""
    without = scoring.weighted_implementation_score(
        {"Implemented": 5, "Not Implemented": 5})
    with_na = scoring.weighted_implementation_score(
        {"Implemented": 5, "Not Implemented": 5, "Not Applicable": 20})
    assert without["score"] == with_na["score"] == 50.0
    assert with_na["excluded"] == 20
    assert with_na["assessed"] == 10


@pytest.mark.whitebox
def test_catalogue_entries_are_never_assessed():
    result = scoring.weighted_implementation_score({"Not Yet In Scope": 40})
    assert result["assessed"] == 0
    assert result["excluded"] == 40


@pytest.mark.whitebox
def test_empty_register_does_not_divide_by_zero():
    result = scoring.weighted_implementation_score({})
    assert result["score"] == 0.0
    assert result["assessed"] == 0


@pytest.mark.whitebox
def test_unrecognised_status_is_refused_not_scored_as_zero():
    """Silently scoring an unknown status as zero would understate the result
    and hide a data problem, so the function must raise instead."""
    with pytest.raises(ValueError, match="unrecognised control status"):
        scoring.weighted_implementation_score({"Almost Done": 3})


@pytest.mark.whitebox
def test_negative_count_is_refused():
    with pytest.raises(ValueError, match="negative control count"):
        scoring.weighted_implementation_score({"Implemented": -1})


# ---------------------------------------------------------------------------
# evidence_coverage
# ---------------------------------------------------------------------------

@pytest.mark.whitebox
def test_evidence_coverage_percentage():
    assert scoring.evidence_coverage(61, 13) == 21.3


@pytest.mark.whitebox
def test_evidence_coverage_of_empty_register_is_zero():
    assert scoring.evidence_coverage(0, 0) == 0.0


@pytest.mark.whitebox
def test_evidence_coverage_cannot_exceed_one_hundred_percent():
    with pytest.raises(ValueError):
        scoring.evidence_coverage(10, 11)


# ---------------------------------------------------------------------------
# classify_due_date: boundary values
# ---------------------------------------------------------------------------

@pytest.mark.whitebox
@pytest.mark.parametrize("offset,expected_state,expected_days", [
    (-30, "overdue", 30),
    (-1, "overdue", 1),
    (0, "due_soon", 0),          # due today is not yet late
    (14, "due_soon", 14),        # last day inside the window
    (15, "on_track", 15),        # first day outside it
    (90, "on_track", 90),
])
def test_due_date_boundaries(today, offset, expected_state, expected_days):
    from datetime import timedelta
    state, days = scoring.classify_due_date(today + timedelta(days=offset), today)
    assert (state, days) == (expected_state, expected_days)


@pytest.mark.whitebox
def test_missing_due_date_is_not_reported_as_overdue(today):
    assert scoring.classify_due_date(None, today) == ("not_scheduled", 0)


# ---------------------------------------------------------------------------
# remediation_exposure
# ---------------------------------------------------------------------------

@pytest.mark.whitebox
def test_closed_items_are_excluded_from_exposure(today):
    from datetime import timedelta
    items = [{"status": "Closed", "priority": "Critical",
              "due_date": today - timedelta(days=60)}]
    summary = scoring.remediation_exposure(items, today)
    assert summary == {"open": 0, "overdue": 0, "due_soon": 0,
                       "exposure_index": 0, "max_days_overdue": 0}


@pytest.mark.whitebox
def test_exposure_weights_priority_not_just_count(today):
    """Two overdue Critical findings must register above five overdue Low ones,
    which a plain count of overdue items would not show."""
    from datetime import timedelta
    past = today - timedelta(days=3)
    two_critical = [{"status": "Open", "priority": "Critical", "due_date": past}] * 2
    five_low = [{"status": "Open", "priority": "Low", "due_date": past}] * 5

    critical = scoring.remediation_exposure(two_critical, today)
    low = scoring.remediation_exposure(five_low, today)

    assert critical["overdue"] < low["overdue"]              # 2 items against 5
    assert critical["exposure_index"] > low["exposure_index"]  # 16 against 5


@pytest.mark.whitebox
def test_exposure_reports_the_longest_slip(today):
    from datetime import timedelta
    items = [{"status": "Open", "priority": "Low", "due_date": today - timedelta(days=4)},
             {"status": "In Progress", "priority": "High",
              "due_date": today - timedelta(days=40)}]
    assert scoring.remediation_exposure(items, today)["max_days_overdue"] == 40


@pytest.mark.whitebox
def test_unknown_priority_still_counts_as_exposure(today):
    """A priority the policy does not list must not silently score nothing."""
    from datetime import timedelta
    items = [{"status": "Open", "priority": "Urgent",
              "due_date": today - timedelta(days=1)}]
    assert scoring.remediation_exposure(items, today)["exposure_index"] >= 1


# ---------------------------------------------------------------------------
# domain_progress
# ---------------------------------------------------------------------------

@pytest.mark.whitebox
def test_domains_are_returned_weakest_first():
    """The dashboard shows this list top down, so the domain needing attention
    must come first rather than whichever name sorts alphabetically."""
    rows = {
        "Cybersecurity Governance": {"Implemented": 9, "Not Implemented": 1},
        "Cybersecurity Defense": {"Implemented": 1, "Not Implemented": 9},
    }
    result = scoring.domain_progress(rows)
    assert [r["domain"] for r in result] == ["Cybersecurity Defense",
                                             "Cybersecurity Governance"]
    assert result[0]["score"] == 10.0
