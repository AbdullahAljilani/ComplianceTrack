"""Remediation Tracker logic.

Designed in Unit 3, left unbuilt in Unit 4, implemented here. A remediation
item records a gap found against a control, who owns fixing it, how urgent it
is, when it is due and whether it is still open.

The overdue rule is derived rather than stored, following the decision taken in
Unit 3: no nightly job sets a flag, and no user can leave one set by hand. An
item is overdue if it is not closed and its due date has passed, evaluated at
the moment it is read. The same rule therefore holds in the tracker list, on
the dashboard and in the scoring service, because all three ask this module.
"""
from datetime import date, datetime, timezone

from src import db
from src.services import audit
from src.services.scoring import PRIORITY_WEIGHTS, classify_due_date

OPEN, IN_PROGRESS, CLOSED = "Open", "In Progress", "Closed"
VALID_STATUSES = (OPEN, IN_PROGRESS, CLOSED)
VALID_PRIORITIES = tuple(PRIORITY_WEIGHTS)
MIN_CLOSURE_NOTE = 10


# ---------------------------------------------------------------------------
# Section 1: pure decisions
# ---------------------------------------------------------------------------

def validate_new_item(finding, priority, due, today):
    """Check a proposed finding before it is written.

    Returns (True, None) or (False, reason). A due date in the past is refused
    at creation: an item that is overdue the moment it is raised carries no
    information about whether anyone is late.
    """
    if len((finding or "").strip()) < 10:
        return False, "Describe the finding in at least 10 characters."
    if priority not in VALID_PRIORITIES:
        return False, f"'{priority}' is not a valid priority."
    if due is None:
        return False, "A remediation item must have a due date."
    if due < today:
        return False, "The due date cannot be in the past."
    return True, None


def can_close(item, actor_id, actor_role, note):
    """Decide whether this user may close this item, and whether it is ready.

    The item owner closes their own work; a GRC Administrator may close any
    item, because someone has to be able to close an item whose owner has left.
    Every closure carries a note, so the register records what was done and not
    merely that something was.
    """
    if item["status"] == CLOSED:
        return False, "This item is already closed."
    is_owner = int(item["owner_user_id"]) == int(actor_id)
    if not (is_owner or actor_role == "GRC Administrator"):
        return False, ("Only the assigned owner or a GRC Administrator may "
                       "close a remediation item.")
    if len((note or "").strip()) < MIN_CLOSURE_NOTE:
        return False, (f"Record what was done, in at least "
                       f"{MIN_CLOSURE_NOTE} characters.")
    return True, None


def prioritise(items, today):
    """Order open work so the most pressing item is first.

    Sorted by state (overdue before due soon before on track), then by priority
    weight descending, then by the earliest due date. A plain sort on due date
    alone would put a Low finding that slipped yesterday above a Critical one
    due tomorrow, which is the wrong way round for the person working the list.
    """
    state_rank = {"overdue": 0, "due_soon": 1, "on_track": 2,
                  "not_scheduled": 3, "closed": 4}

    def key(item):
        if item["status"] == CLOSED:
            return (state_rank["closed"], 0, date.max)
        state, _ = classify_due_date(item["due_date"], today)
        weight = PRIORITY_WEIGHTS.get(item["priority"], 1)
        return (state_rank[state], -weight, item["due_date"] or date.max)

    return sorted(items, key=key)


def annotate(items, today):
    """Attach the derived state and day count to each item for display."""
    out = []
    for item in items:
        row = dict(item)
        if row["status"] == CLOSED:
            row["derived_state"], row["derived_days"] = "closed", 0
        else:
            row["derived_state"], row["derived_days"] = classify_due_date(
                row["due_date"], today)
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Section 2: storage
# ---------------------------------------------------------------------------

def list_items(status_filter=None, today=None):
    where, params = ["1 = 1"], []
    if status_filter in VALID_STATUSES:
        where.append("r.status = %s")
        params.append(status_filter)
    rows = db.query(
        f"""
        SELECT r.remediation_id, r.control_id, r.finding, r.priority,
               r.due_date, r.status, r.closure_note, r.closed_at,
               c.ecc_reference, c.domain,
               ow.full_name AS owner_name, r.owner_user_id
        FROM remediation_items r
        JOIN controls c ON c.control_id = r.control_id
        JOIN users ow ON ow.user_id = r.owner_user_id
        WHERE {' AND '.join(where)}
        """,
        tuple(params),
    )
    today = today or date.today()
    return prioritise(annotate(rows, today), today)


def list_for_control(control_id, today=None):
    rows = db.query(
        """
        SELECT r.remediation_id, r.finding, r.priority, r.due_date, r.status,
               r.owner_user_id, ow.full_name AS owner_name
        FROM remediation_items r
        JOIN users ow ON ow.user_id = r.owner_user_id
        WHERE r.control_id = %s
        """,
        (control_id,),
    )
    today = today or date.today()
    return prioritise(annotate(rows, today), today)


def create_item(control_id, finding, owner_user_id, priority, due, actor_id,
                today=None):
    ok, reason = validate_new_item(finding, priority, due, today or date.today())
    if not ok:
        return None, reason

    control = db.query_one(
        "SELECT ecc_reference, scope_tier FROM controls WHERE control_id = %s",
        (control_id,),
    )
    if control is None:
        return None, "That control does not exist."
    if control["scope_tier"] != "in_scope":
        return None, ("Catalogue-only entries are not assessed, so no "
                      "remediation item can be raised against them.")

    row = db.query_one(
        """
        INSERT INTO remediation_items (control_id, finding, owner_user_id,
                                       priority, due_date, status)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING remediation_id
        """,
        (control_id, finding.strip(), owner_user_id, priority, due, OPEN),
    )
    audit.record("REMEDIATION_CREATE", "remediation", row["remediation_id"],
                 {"control": control["ecc_reference"], "priority": priority,
                  "due": str(due)}, user_id=actor_id)
    return row["remediation_id"], None


def close_item(remediation_id, actor_id, actor_role, note):
    item = db.query_one(
        """
        SELECT r.remediation_id, r.status, r.owner_user_id, c.ecc_reference
        FROM remediation_items r JOIN controls c ON c.control_id = r.control_id
        WHERE r.remediation_id = %s
        """,
        (remediation_id,),
    )
    if item is None:
        return False, "That remediation item does not exist."

    ok, reason = can_close(item, actor_id, actor_role, note)
    if not ok:
        return False, reason

    db.execute(
        """
        UPDATE remediation_items
        SET status = %s, closed_by = %s, closed_at = %s, closure_note = %s,
            updated_at = now()
        WHERE remediation_id = %s
        """,
        (CLOSED, actor_id, datetime.now(timezone.utc), note.strip()[:1000],
         remediation_id),
    )
    audit.record("REMEDIATION_CLOSE", "remediation", remediation_id,
                 {"control": item["ecc_reference"]}, user_id=actor_id)
    return True, f"Remediation item {remediation_id} closed."


def advance_item(remediation_id, new_status, actor_id):
    if new_status not in (OPEN, IN_PROGRESS):
        return False, "Use the closure form to close an item."
    updated = db.execute(
        """
        UPDATE remediation_items SET status = %s, updated_at = now()
        WHERE remediation_id = %s AND status <> %s
        """,
        (new_status, remediation_id, CLOSED),
    )
    if not updated:
        return False, "That item could not be updated."
    audit.record("REMEDIATION_UPDATE", "remediation", remediation_id,
                 {"to": new_status}, user_id=actor_id)
    return True, f"Item moved to {new_status}."
