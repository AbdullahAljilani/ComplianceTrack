"""Remediation Tracker routes. Web layer only; the rules live in service.py."""
from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

from src import db
from src.remediation_tracker import service
from src.services.auth import current_user, requires

bp = Blueprint("remediation", __name__, url_prefix="/remediation")


def _parse_date(raw):
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


@bp.route("/")
@requires("remediation.view")
def index():
    status = request.args.get("status", "").strip()
    items = service.list_items(status_filter=status or None)
    counts = db.query(
        "SELECT status, COUNT(*) AS n FROM remediation_items GROUP BY status"
    )
    return render_template(
        "remediation/list.html", items=items,
        counts={r["status"]: r["n"] for r in counts},
        filter_status=status,
        overdue=sum(1 for i in items if i["derived_state"] == "overdue"),
        today=date.today(),
    )


@bp.route("/new", methods=["GET", "POST"])
@requires("remediation.edit")
def new():
    controls = db.query(
        "SELECT control_id, ecc_reference, description FROM controls "
        "WHERE scope_tier = 'in_scope' "
        "ORDER BY string_to_array(ecc_reference, '-')::int[]"
    )
    owners = db.query(
        "SELECT user_id, full_name FROM users WHERE is_active ORDER BY full_name"
    )

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


@bp.route("/<int:remediation_id>/close", methods=["POST"])
@requires("remediation.edit")
def close(remediation_id):
    user = current_user()
    ok, message = service.close_item(remediation_id, user["user_id"],
                                     user["role"], request.form.get("note", ""))
    flash(message, "success" if ok else "danger")
    return redirect(url_for("remediation.index"))


@bp.route("/<int:remediation_id>/status", methods=["POST"])
@requires("remediation.edit")
def advance(remediation_id):
    ok, message = service.advance_item(remediation_id,
                                       request.form.get("status", ""),
                                       current_user()["user_id"])
    flash(message, "success" if ok else "danger")
    return redirect(url_for("remediation.index"))
