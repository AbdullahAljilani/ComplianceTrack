"""Control Register module.

Holds one record per ECC-2:2024 main control: its identifier, domain, subdomain,
owner, implementation status and review date. Reads and writes go through the
data layer as bound parameters, and every state change goes through the shared
audit service.
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from src import db
from src.evidence_management import service as evidence_service
from src.remediation_tracker import service as remediation_service
from src.services import audit
from src.services.auth import current_user, may_change_control, requires

bp = Blueprint("controls", __name__, url_prefix="/controls")

ASSESSABLE_STATUSES = [
    "Not Implemented", "Partially Implemented", "Implemented",
    "Not Applicable", "Evidence Missing",
]
PAGE_SIZE = 25


@bp.route("/")
@requires("control.view")
def index():
    domain = request.args.get("domain", "").strip()
    status = request.args.get("status", "").strip()
    tier = request.args.get("tier", "in_scope").strip()
    search = request.args.get("q", "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    # Filters are appended as parameter placeholders only; the values themselves
    # are always bound, never interpolated into the SQL text.
    where, params = ["1 = 1"], []
    if domain:
        where.append("c.domain = %s")
        params.append(domain)
    if status:
        where.append("c.status = %s")
        params.append(status)
    if tier in ("in_scope", "catalog_only"):
        where.append("c.scope_tier = %s")
        params.append(tier)
    if search:
        where.append("(c.ecc_reference ILIKE %s OR c.description ILIKE %s"
                     " OR c.subdomain ILIKE %s)")
        params.extend([f"%{search}%"] * 3)
    clause = " AND ".join(where)

    total = db.query_one(
        f"SELECT COUNT(*) AS n FROM controls c WHERE {clause}", tuple(params)
    )["n"]
    rows = db.query(
        f"""
        SELECT c.control_id, c.ecc_reference, c.domain, c.subdomain,
               c.description, c.status, c.review_date, c.scope_tier,
               u.full_name AS owner_name
        FROM controls c
        LEFT JOIN users u ON u.user_id = c.owner_user_id
        WHERE {clause}
        ORDER BY string_to_array(c.ecc_reference, '-')::int[]
        LIMIT %s OFFSET %s
        """,
        tuple(params) + (PAGE_SIZE, (page - 1) * PAGE_SIZE),
    )

    domains = [r["domain"] for r in db.query(
        "SELECT DISTINCT domain FROM controls ORDER BY domain")]

    return render_template(
        "controls/list.html", controls=rows, domains=domains,
        statuses=ASSESSABLE_STATUSES, total=total, page=page,
        pages=max(1, -(-total // PAGE_SIZE)),
        filters={"domain": domain, "status": status, "tier": tier, "q": search},
    )


@bp.route("/<int:control_id>")
@requires("control.view")
def detail(control_id):
    control = db.query_one(
        """
        SELECT c.*, u.full_name AS owner_name
        FROM controls c
        LEFT JOIN users u ON u.user_id = c.owner_user_id
        WHERE c.control_id = %s
        """,
        (control_id,),
    )
    if control is None:
        return render_template("404.html"), 404
    history = db.query(
        """
        SELECT a.action, a.occurred_at, a.details, u.username
        FROM audit_log a
        LEFT JOIN users u ON u.user_id = a.user_id
        WHERE a.entity_type = 'control' AND a.entity_id = %s
        ORDER BY a.occurred_at DESC
        LIMIT 20
        """,
        (control_id,),
    )
    # Unit 5: both figures now come from the modules that own them rather than
    # from a query repeated here, so one rule change updates every caller.
    approved_evidence = evidence_service.approved_count(control_id)
    remediation = remediation_service.list_for_control(control_id)
    return render_template("controls/detail.html", control=control,
                           statuses=ASSESSABLE_STATUSES, history=history,
                           approved_evidence=approved_evidence,
                           remediation=remediation,
                           may_change=may_change_control(current_user(),
                                                         control["owner_user_id"]))


@bp.route("/<int:control_id>/status", methods=["POST"])
@requires("control.edit")
def update_status(control_id):
    new_status = request.form.get("status", "")
    control = db.query_one(
        "SELECT ecc_reference, status, scope_tier, owner_user_id "
        "FROM controls WHERE control_id = %s",
        (control_id,),
    )
    if control is None:
        return render_template("404.html"), 404

    if control["scope_tier"] != "in_scope":
        flash("This entry is listed for framework reference only and is not "
              "assessed by this prototype.", "warning")
        return redirect(url_for("controls.detail", control_id=control_id))

    # Unit 6: the role check above admits every Control Owner. FR-1 limits a
    # change to the owner assigned to this control or a GRC Administrator, so
    # the record itself is checked as well, on the server, before anything else.
    if not may_change_control(current_user(), control["owner_user_id"]):
        return render_template(
            "403.html",
            reason=(f"Only the owner assigned to {control['ecc_reference']} or a "
                    f"GRC Administrator can change its status.")), 403

    if new_status not in ASSESSABLE_STATUSES:
        flash("That is not a valid implementation status.", "danger")
        return redirect(url_for("controls.detail", control_id=control_id))

    # Unit 3 design rule: a control reaches 'Implemented' only once evidence
    # supporting it has been approved by a reviewer. Enforced in the application
    # layer, not merely hidden in the interface.
    if new_status == "Implemented":
        if evidence_service.approved_count(control_id) == 0:
            flash("A control cannot be marked Implemented until supporting "
                  "evidence has been approved by a reviewer.", "danger")
            return redirect(url_for("controls.detail", control_id=control_id))

    if new_status == control["status"]:
        flash("Status unchanged.", "secondary")
        return redirect(url_for("controls.detail", control_id=control_id))

    previous = control["status"]
    db.execute(
        "UPDATE controls SET status = %s, updated_at = now() WHERE control_id = %s",
        (new_status, control_id),
    )
    audit.record(
        audit.STATUS_CHANGE, "control", control_id,
        {"ecc_reference": control["ecc_reference"],
         "from": previous, "to": new_status,
         "by": current_user()["username"]},
    )
    flash(f"{control['ecc_reference']} moved from {previous} to {new_status}.", "success")
    return redirect(url_for("controls.detail", control_id=control_id))
