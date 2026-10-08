"""Remediation Tracker logic.

Designed in Unit 3, left unbuilt in Unit 4, implemented in Unit 5, and brought
into line with FR-7 in Unit 6. A remediation item records a gap found against
a control, who owns fixing it, how urgent it is, when it is due and where it
stands.

The overdue rule is derived rather than stored, following the decision taken in
Unit 3: no nightly job sets a flag, and no user can leave one set by hand. An
item is overdue if it is not closed and its due date has passed, evaluated at
the moment it is read. The same rule therefore holds in the tracker list, on
the dashboard and in the scoring service, because all three ask this module.

Closure takes two people (Unit 6). The owner, or a GRC Administrator acting
for an owner who has left, records what was done and requests closure; the
item waits in Pending Verification until someone else who holds the
verification permission either verifies it or returns it with a reason. FR-7
asks for exactly this, and the database refuses a closed item that the owner
or the requester closed, so the rule holds even against a direct change.
"""
from datetime import date, datetime, timezone

from src import db
from src.services import audit
from src.services.scoring import PRIORITY_WEIGHTS, classify_due_date

OPEN, IN_PROGRESS, PENDING, CLOSED = ("Open", "In Progress",
                                      "Pending Verification", "Closed")
VALID_STATUSES = (OPEN, IN_PROGRESS, PENDING, CLOSED)
VALID_PRIORITIES = tuple(PRIORITY_WEIGHTS)
MIN_CLOSURE_NOTE = 10
PAGE_SIZE = 25
# Roles that can carry a remediation item through to a closure request. An item
# assigned to anyone else could never be finished, so the owner must hold one.
OWNER_ROLES = ("Control Owner", "GRC Administrator")


# ---------------------------------------------------------------------------
# Section 1: pure decisions
# ---------------------------------------------------------------------------

def validate_new_item(finding, owner_user_id, priority, due, today):
    """Check a proposed finding before it is written.

    Returns (True, None) or (False, reason). A due date in the past is refused
    at creation: an item that is overdue the moment it is raised carries no
    information about whether anyone is late.

    The owner check was added in Unit 5 after a test submitted the form without
    the owner field. The browser marks that field required, but that is
    presentation, and a request built by hand simply omits it. Without this
    check the missing value reached the database and raised an unhandled
    not-null violation, which the user saw as a server error.
    """
    if len((finding or "").strip()) < 10:
        return False, "Describe the finding in at least 10 characters."
    if owner_user_id is None:
        return False, "A remediation item must be assigned to an owner."
    if priority not in VALID_PRIORITIES:
        return False, f"'{priority}' is not a valid priority."
    if due is None:
        return False, "A remediation item must have a due date."
    if due < today:
        return False, "The due date cannot be in the past."
    return True, None


def _is_owner_or_admin(item, actor_id, actor_role):
    return (int(item["owner_user_id"]) == int(actor_id)
            or actor_role == "GRC Administrator")


def can_advance(item, actor_id, actor_role, new_status):
    """Moving work between Open and In Progress is the owner's call.

    An item awaiting verification or already closed is not moved back by hand:
    only the verifier returns a claim, so the record of who decided what stays
    intact.
    """
    if new_status not in (OPEN, IN_PROGRESS):
        return False, "Use the closure request to finish an item."
    if item["status"] in (PENDING, CLOSED):
        return False, f"An item that is {item['status'].lower()} cannot be moved by hand."
    if item["status"] == new_status:
        return False, f"The item is already {new_status.lower()}."
    if not _is_owner_or_admin(item, actor_id, actor_role):
        return False, ("Only the assigned owner or a GRC Administrator may "
                       "update this item.")
    return True, None


def can_request_closure(item, actor_id, actor_role, note):
    """Decide whether this user may ask for this item to be closed.

    The item owner requests closure of their own work; a GRC Administrator may
    request it for any item, because someone has to be able to finish an item
    whose owner has left. Every request carries a note, so the register
    records what was done and not merely that something was. (Unit 5 called
    this can_close and let the request close the item outright.)
    """
    if item["status"] == CLOSED:
        return False, "This item is already closed."
    if item["status"] == PENDING:
        return False, "Closure has already been requested and is awaiting verification."
    if not _is_owner_or_admin(item, actor_id, actor_role):
        return False, ("Only the assigned owner or a GRC Administrator may "
                       "request closure of a remediation item.")
    if len((note or "").strip()) < MIN_CLOSURE_NOTE:
        return False, (f"Record what was done, in at least "
                       f"{MIN_CLOSURE_NOTE} characters.")
    return True, None


def can_verify_closure(item, actor_id, decision, note):
    """Decide whether this user may verify, or return, a closure request.

    FR-7: the verifier must be someone other than the item's owner and other
    than whoever requested the closure. Returning a claim needs a reason the
    owner can act on; verifying one may carry a note but does not need one.
    """
    if item["status"] != PENDING:
        return False, "This item is not awaiting verification."
    if decision not in ("approve", "return"):
        return False, "That is not a valid verification decision."
    involved = {int(item["owner_user_id"])}
    if item.get("closure_requested_by") is not None:
        involved.add(int(item["closure_requested_by"]))
    if int(actor_id) in involved:
        return False, ("Closure must be verified by someone other than the "
                       "item's owner and the person who requested it.")
    if decision == "return" and len((note or "").strip()) < MIN_CLOSURE_NOTE:
        return False, (f"Record why the item is being returned, in at least "
                       f"{MIN_CLOSURE_NOTE} characters.")
    return True, None


def prioritise(items, today):
    """Order open work so the most pressing item is first.

    Sorted by state (overdue before due soon before on track), then by priority
    weight descending, then by the earliest due date. A plain sort on due date
    alone would put a Low finding that slipped yesterday above a Critical one
    due tomorrow, which is the wrong way round for the person working the list.
    An item awaiting verification is still open work: it is ranked by its due
    date like any other until someone verifies it.
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


def paginate(items, page, size=PAGE_SIZE):
    """Return (the items on this page, the page number used, the page count).

    Added in Unit 6 after the scale evaluation: the tracker rendered every item
    on one page, so its response grew in step with the register (about 1.6 s
    and 23 MB of HTML at 20,000 items). Ordering still happens over the whole
    list, so the most pressing item is on page one whatever page is shown.
    """
    pages = max(1, -(-len(items) // size))
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    page = min(max(1, page), pages)
    start = (page - 1) * size
    return items[start:start + size], page, pages


# ---------------------------------------------------------------------------
# Section 2: storage
# ---------------------------------------------------------------------------

_LIST_SQL = """
    SELECT r.remediation_id, r.control_id, r.finding, r.priority,
           r.due_date, r.status, r.closure_note, r.closed_at,
           r.closure_requested_at, r.verification_note,
           r.owner_user_id, r.closure_requested_by, r.closed_by,
           c.ecc_reference, c.domain,
           ow.full_name AS owner_name,
           rq.full_name AS requested_by_name,
           vf.full_name AS verified_by_name
    FROM remediation_items r
    JOIN controls c ON c.control_id = r.control_id
    JOIN users ow ON ow.user_id = r.owner_user_id
    LEFT JOIN users rq ON rq.user_id = r.closure_requested_by
    LEFT JOIN users vf ON vf.user_id = r.closed_by
"""


def list_items(status_filter=None, owner_id=None, today=None):
    where, params = ["1 = 1"], []
    if status_filter in VALID_STATUSES:
        where.append("r.status = %s")
        params.append(status_filter)
    if owner_id is not None:
        where.append("r.owner_user_id = %s")
        params.append(owner_id)
    rows = db.query(_LIST_SQL + f" WHERE {' AND '.join(where)}", tuple(params))
    today = today or date.today()
    return prioritise(annotate(rows, today), today)


def list_for_control(control_id, today=None):
    rows = db.query(_LIST_SQL + " WHERE r.control_id = %s", (control_id,))
    today = today or date.today()
    return prioritise(annotate(rows, today), today)


def eligible_owners():
    """Active users who can carry an item through to a closure request."""
    return db.query(
        """
        SELECT u.user_id, u.full_name, r.role_name
        FROM users u JOIN roles r ON r.role_id = u.role_id
        WHERE u.is_active AND r.role_name = ANY(%s)
        ORDER BY u.full_name
        """,
        (list(OWNER_ROLES),),
    )


def create_item(control_id, finding, owner_user_id, priority, due, actor_id,
                today=None):
    ok, reason = validate_new_item(finding, owner_user_id, priority, due,
                                   today or date.today())
    if not ok:
        return None, reason

    control = db.query_one(
        "SELECT ecc_reference, scope_tier FROM controls WHERE control_id = %s",
        (control_id,),
    )
    if control is None:
        return None, "That control does not exist."
    owner = db.query_one(
        """
        SELECT u.user_id, r.role_name FROM users u
        JOIN roles r ON r.role_id = u.role_id
        WHERE u.user_id = %s AND u.is_active
        """,
        (owner_user_id,),
    )
    if owner is None:
        return None, "That owner is not an active user."
    if owner["role_name"] not in OWNER_ROLES:
        return None, ("A remediation item must be owned by a Control Owner or a "
                      "GRC Administrator, who can see it through to closure.")
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


def _load(remediation_id):
    return db.query_one(
        """
        SELECT r.remediation_id, r.status, r.owner_user_id,
               r.closure_requested_by, r.closure_note, c.ecc_reference
        FROM remediation_items r JOIN controls c ON c.control_id = r.control_id
        WHERE r.remediation_id = %s
        """,
        (remediation_id,),
    )


def advance_item(remediation_id, new_status, actor_id, actor_role):
    item = _load(remediation_id)
    if item is None:
        return False, "That remediation item does not exist."
    ok, reason = can_advance(item, actor_id, actor_role, new_status)
    if not ok:
        return False, reason
    db.execute(
        "UPDATE remediation_items SET status = %s, updated_at = now() "
        "WHERE remediation_id = %s",
        (new_status, remediation_id),
    )
    audit.record("REMEDIATION_UPDATE", "remediation", remediation_id,
                 {"control": item["ecc_reference"], "to": new_status},
                 user_id=actor_id)
    return True, f"Item {remediation_id} moved to {new_status}."


def request_closure(remediation_id, actor_id, actor_role, note):
    item = _load(remediation_id)
    if item is None:
        return False, "That remediation item does not exist."
    ok, reason = can_request_closure(item, actor_id, actor_role, note)
    if not ok:
        return False, reason
    db.execute(
        """
        UPDATE remediation_items
        SET status = %s, closure_note = %s, closure_requested_by = %s,
            closure_requested_at = %s, verification_note = NULL,
            updated_at = now()
        WHERE remediation_id = %s
        """,
        (PENDING, note.strip()[:1000], actor_id, datetime.now(timezone.utc),
         remediation_id),
    )
    audit.record("REMEDIATION_CLOSURE_REQUEST", "remediation", remediation_id,
                 {"control": item["ecc_reference"]}, user_id=actor_id)
    return True, (f"Closure of item {remediation_id} requested. It stays open "
                  f"until someone else verifies it.")


def verify_closure(remediation_id, actor_id, decision, note):
    item = _load(remediation_id)
    if item is None:
        return False, "That remediation item does not exist."
    decision = str(decision or "").lower()
    ok, reason = can_verify_closure(item, actor_id, decision, note)
    if not ok:
        return False, reason

    if decision == "approve":
        db.execute(
            """
            UPDATE remediation_items
            SET status = %s, closed_by = %s, closed_at = %s,
                verification_note = %s, updated_at = now()
            WHERE remediation_id = %s
            """,
            (CLOSED, actor_id, datetime.now(timezone.utc),
             (note or "").strip()[:1000] or None, remediation_id),
        )
        audit.record("REMEDIATION_CLOSE", "remediation", remediation_id,
                     {"control": item["ecc_reference"], "verified": True},
                     user_id=actor_id)
        return True, f"Item {remediation_id} verified and closed."

    db.execute(
        """
        UPDATE remediation_items
        SET status = %s, verification_note = %s, closure_note = NULL,
            closure_requested_by = NULL, closure_requested_at = NULL,
            updated_at = now()
        WHERE remediation_id = %s
        """,
        (IN_PROGRESS, note.strip()[:1000], remediation_id),
    )
    audit.record("REMEDIATION_RETURN", "remediation", remediation_id,
                 {"control": item["ecc_reference"],
                  "claim": (item["closure_note"] or "")[:200]},
                 user_id=actor_id)
    return True, f"Item {remediation_id} returned to its owner."
