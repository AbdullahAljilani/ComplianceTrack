"""Compliance scoring service.

This module holds the central calculation of ComplianceTrack. The Control
Register records what each control's implementation status is; this service
turns those records into the tracking indicators the Reporting Dashboard
presents.

Two design rules shape it.

First, every indicator is derived on read. Nothing here is stored back onto the
control row, so a rejected piece of evidence or a newly overdue remediation item
changes the reported figure the moment it happens, with no cached value to fall
out of step. This is the same rule the Unit 3 design applied to the overdue
view, applied consistently.

Second, the calculation is separated from the database. Every function in the
first section below is pure: it takes plain values and returns plain values,
touching no connection, no request and no clock it was not given. That is what
makes the logic testable in isolation, which is the property unit testing
depends on (Amazon Web Services, n.d.). The database-backed functions in the
second section only gather rows and hand them to the pure functions.

The output is tracking information. A score produced here is a summary of what
has been recorded in the system. It is not an assessment, and it does not
certify compliance with NCA ECC-2:2024.
"""
from datetime import date

from src import db

# ---------------------------------------------------------------------------
# Policy constants
# ---------------------------------------------------------------------------

# Partial credit per recorded status. A control marked Implemented has been
# through the evidence gate, so it earns full weight. Partially Implemented
# earns half. Evidence Missing earns a quarter: work has been claimed but
# nothing supports it yet, so it is worth more than nothing and much less than
# a verified control.
STATUS_WEIGHTS = {
    "Implemented": 1.00,
    "Partially Implemented": 0.50,
    "Evidence Missing": 0.25,
    "Not Implemented": 0.00,
}

# Not Applicable is excluded from the numerator and the denominator alike, so
# scoping a control out neither rewards nor penalises the entity. Catalogue
# entries carry 'Not Yet In Scope' and are never assessed at all.
EXCLUDED_FROM_SCORE = ("Not Applicable", "Not Yet In Scope")

# Relative weight of a remediation item by priority, used for the exposure
# index. The steps are deliberately coarse; a finer scale would imply a
# precision the underlying judgement does not have.
PRIORITY_WEIGHTS = {"Low": 1, "Medium": 2, "High": 4, "Critical": 8}

# A remediation item or a control review inside this window is reported as
# approaching rather than comfortable, so owners see it before it slips.
DUE_SOON_DAYS = 14


# ---------------------------------------------------------------------------
# Section 1: pure calculation, no database, no clock
# ---------------------------------------------------------------------------

def weighted_implementation_score(status_counts):
    """Return the weighted implementation score for a set of controls.

    status_counts maps a status name to how many controls hold it. The return
    value is a dict carrying the score and the figures it was derived from, so
    the dashboard can show the working rather than a bare percentage.

    Raises ValueError on a status the policy does not recognise, rather than
    silently scoring it as zero and understating the result.
    """
    assessed = 0
    earned = 0.0
    excluded = 0

    for status, count in status_counts.items():
        if count < 0:
            raise ValueError(f"negative control count for status {status!r}")
        if status in EXCLUDED_FROM_SCORE:
            excluded += count
            continue
        if status not in STATUS_WEIGHTS:
            raise ValueError(f"unrecognised control status {status!r}")
        assessed += count
        earned += STATUS_WEIGHTS[status] * count

    score = round(earned / assessed * 100, 1) if assessed else 0.0
    return {
        "score": score,
        "assessed": assessed,
        "excluded": excluded,
        "weighted_total": round(earned, 2),
    }


def evidence_coverage(assessed_controls, controls_with_approved_evidence):
    """Percentage of assessed controls holding at least one approved record.

    Reported beside the implementation score rather than folded into it. A high
    implementation score sitting on thin evidence coverage is exactly the
    condition a reviewer needs to be able to see.
    """
    if assessed_controls < 0 or controls_with_approved_evidence < 0:
        raise ValueError("counts cannot be negative")
    if controls_with_approved_evidence > assessed_controls:
        raise ValueError("evidenced controls cannot exceed assessed controls")
    if assessed_controls == 0:
        return 0.0
    return round(controls_with_approved_evidence / assessed_controls * 100, 1)


def classify_due_date(due, today, window=DUE_SOON_DAYS):
    """Classify a due date as overdue, due_soon or on_track.

    Returns (state, days), where days is always a positive magnitude: days
    past the date when overdue, days remaining otherwise. 'today' is passed in
    rather than read from the system clock so the behaviour is reproducible
    under test.
    """
    if due is None:
        return ("not_scheduled", 0)
    delta = (due - today).days
    if delta < 0:
        return ("overdue", -delta)
    if delta <= window:
        return ("due_soon", delta)
    return ("on_track", delta)


def remediation_exposure(items, today):
    """Summarise open remediation work as counts and a weighted exposure index.

    items is a sequence of mappings carrying at least 'status', 'priority' and
    'due_date'. Closed items are ignored. The exposure index is the sum of the
    priority weights of the overdue items, so two overdue Critical findings
    (8 + 8) register more strongly than five overdue Low ones (5), which a plain
    count of overdue items would not show.
    """
    summary = {"open": 0, "overdue": 0, "due_soon": 0,
               "exposure_index": 0, "max_days_overdue": 0}

    for item in items:
        if item["status"] == "Closed":
            continue
        summary["open"] += 1
        state, days = classify_due_date(item["due_date"], today)
        if state == "overdue":
            summary["overdue"] += 1
            summary["exposure_index"] += PRIORITY_WEIGHTS.get(item["priority"], 1)
            summary["max_days_overdue"] = max(summary["max_days_overdue"], days)
        elif state == "due_soon":
            summary["due_soon"] += 1

    return summary


def domain_progress(rows):
    """Score each domain independently and sort weakest first.

    rows is a sequence of mappings of domain -> status -> count. Ordering the
    output by score puts the domain needing attention at the top of the
    dashboard instead of leaving it in alphabetical order.
    """
    out = []
    for domain, counts in rows.items():
        result = weighted_implementation_score(counts)
        result["domain"] = domain
        out.append(result)
    return sorted(out, key=lambda r: (r["score"], r["domain"]))


# ---------------------------------------------------------------------------
# Section 2: database-backed gathering. These functions read rows and delegate
# every calculation above.
# ---------------------------------------------------------------------------

def _status_counts(domain=None):
    sql = """
        SELECT status, COUNT(*) AS n
        FROM controls
        WHERE scope_tier = 'in_scope'
        {extra}
        GROUP BY status
    """
    params = ()
    if domain:
        sql = sql.format(extra="AND domain = %s")
        params = (domain,)
    else:
        sql = sql.format(extra="")
    return {r["status"]: r["n"] for r in db.query(sql, params)}


def overall_score():
    return weighted_implementation_score(_status_counts())


def score_by_domain():
    rows = db.query(
        """
        SELECT domain, status, COUNT(*) AS n
        FROM controls
        WHERE scope_tier = 'in_scope'
        GROUP BY domain, status
        """
    )
    grouped = {}
    for r in rows:
        grouped.setdefault(r["domain"], {})[r["status"]] = r["n"]
    return domain_progress(grouped)


def coverage_figures():
    row = db.query_one(
        """
        SELECT
          COUNT(*) FILTER (WHERE c.status NOT IN ('Not Applicable','Not Yet In Scope'))
            AS assessed,
          COUNT(*) FILTER (WHERE c.status NOT IN ('Not Applicable','Not Yet In Scope')
                             AND cov.approved_count > 0)
            AS evidenced
        FROM controls c
        JOIN v_control_evidence_coverage cov ON cov.control_id = c.control_id
        WHERE c.scope_tier = 'in_scope'
        """
    )
    return {
        "assessed": row["assessed"],
        "evidenced": row["evidenced"],
        "percent": evidence_coverage(row["assessed"], row["evidenced"]),
    }


def remediation_figures(today=None):
    items = db.query(
        "SELECT status, priority, due_date FROM remediation_items"
    )
    return remediation_exposure(items, today or date.today())


def controls_due_review():
    return db.query_one(
        "SELECT COUNT(*) AS n FROM v_controls_due_review"
    )["n"]


def dashboard_summary(today=None):
    """Assemble every indicator the Reporting Dashboard presents."""
    return {
        "implementation": overall_score(),
        "by_domain": score_by_domain(),
        "evidence": coverage_figures(),
        "remediation": remediation_figures(today),
        "due_review": controls_due_review(),
    }
