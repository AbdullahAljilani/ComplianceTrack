"""Remediation Tracker routes. Web layer only; the rules live in service.py."""
from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from src import db
from src.remediation_tracker import service
from src.services import scoring
from src.services.auth import current_user, requires

bp = Blueprint("remediation", __name__, url_prefix="/remediation")


def _parse_date(raw):
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _back():
    """Return to the list the user was working from, filters and page kept."""
    target = request.form.get("back", "")
    if target.startswith("/remediation/") and "//" not in target:
        return redirect(target)
    return redirect(url_for("remediation.index"))


@bp.route("/")
@requires("remediation.view")
def index():
    status = request.args.get("status", "").strip()
    mine = request.args.get("mine") == "1"
    user = current_user()
    items = service.list_items(status_filter=status or None,
                               owner_id=user["user_id"] if mine else None)
    shown, page, pages = service.paginate(items, request.args.get("page", 1))
    counts = db.query(
        "SELECT status, COUNT(*) AS n FROM remediation_items GROUP BY status"
    )
    # The tiles describe the whole register, so the overdue tile is counted
    # over every item, by the same rule the dashboard uses, not over the
    # filtered list. Unit 6 heuristic review: under a filter it used to drop
    # to the filtered figure while the tiles beside it did not.
    everything = db.query("SELECT status, priority, due_date FROM remediation_items")
    overdue = scoring.remediation_exposure(everything, date.today())["overdue"]
    return render_template(
        "remediation/list.html", items=shown, total=len(items), page=page,
        pages=pages, counts={r["status"]: r["n"] for r in counts},
        filter_status=status, mine=mine, overdue=overdue,
        today=date.today(), back=request.full_path.rstrip("?"),
    )


@bp.route("/new", methods=["GET", "POST"])
@requires("remediation.edit")
def new():
    controls = db.query(
        "SELECT control_id, ecc_reference, description FROM controls "
        "WHERE scope_tier = 'in_scope' "
        "ORDER BY string_to_array(ecc_reference, '-')::int[]"
    )
    owners = service.eligible_owners()

    if request.method == "POST":
        remediation_id, reason = service.create_item(
            control_id=request.form.get("control_id", type=int),
            finding=request.form.get("finding", ""),
            owner_user_id=request.form.get("owner_user_id", type=int),
            priority=request.form.get("priority", ""),
            due=_parse_date(request.form.get("due_date")),
            actor_id=current_user()["user_id"],
        )
        if reason:
            flash(reason, "danger")
            return render_template("remediation/new.html", controls=controls,
                                   owners=owners, priorities=service.VALID_PRIORITIES,
                                   form=request.form), 400
        flash(f"Remediation item {remediation_id} raised.", "success")
        return redirect(url_for("remediation.index"))

    return render_template("remediation/new.html", controls=controls,
                           owners=owners, priorities=service.VALID_PRIORITIES,
                           form={})


@bp.route("/<int:remediation_id>/status", methods=["POST"])
@requires("remediation.edit")
def advance(remediation_id):
    user = current_user()
    ok, message = service.advance_item(remediation_id,
                                       request.form.get("status", ""),
                                       user["user_id"], user["role"])
    flash(message, "success" if ok else "danger")
    return _back()


@bp.route("/<int:remediation_id>/request-closure", methods=["POST"])
@requires("remediation.edit")
def request_closure(remediation_id):
    user = current_user()
    ok, message = service.request_closure(remediation_id, user["user_id"],
                                          user["role"], request.form.get("note", ""))
    flash(message, "success" if ok else "danger")
    return _back()


@bp.route("/<int:remediation_id>/verify", methods=["POST"])
@requires("remediation.verify")
def verify(remediation_id):
    ok, message = service.verify_closure(remediation_id, current_user()["user_id"],
                                         request.form.get("decision", ""),
                                         request.form.get("note", ""))
    flash(message, "success" if ok else "danger")
    return _back()
