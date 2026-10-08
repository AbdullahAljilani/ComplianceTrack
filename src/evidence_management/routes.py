"""Evidence Management routes.

Thin web layer. Every rule lives in service.py; these views read the request,
call the service and render the outcome, so the same rules apply however the
module is driven.
"""
from flask import (Blueprint, current_app, flash, redirect, render_template,
                   request, url_for)

from src import db
from src.evidence_management import service
from src.services.auth import current_user, requires

bp = Blueprint("evidence", __name__, url_prefix="/evidence")


@bp.route("/control/<int:control_id>")
@requires("evidence.view")
def for_control(control_id):
    control = db.query_one(
        "SELECT control_id, ecc_reference, description, status, scope_tier "
        "FROM controls WHERE control_id = %s",
        (control_id,),
    )
    if control is None:
        return render_template("404.html"), 404
    return render_template(
        "evidence/list.html", control=control,
        records=service.list_for_control(control_id),
        allowed=sorted(service.ALLOWED_EXTENSIONS),
        max_mb=service.MAX_UPLOAD_BYTES // (1024 * 1024),
    )


@bp.route("/control/<int:control_id>/upload", methods=["POST"])
@requires("evidence.upload")
def upload(control_id):
    uploaded = request.files.get("document")
    if uploaded is None or not uploaded.filename:
        flash("Choose a file to upload.", "danger")
        return redirect(url_for("evidence.for_control", control_id=control_id))

    # Read once, into memory, so the size check and the digest see exactly the
    # same bytes that are written to disk.
    data = uploaded.read()
    evidence_id, reason = service.store_evidence(
        control_id=control_id,
        uploader_id=current_user()["user_id"],
        original_name=uploaded.filename,
        data=data,
        description=request.form.get("description", ""),
        storage_root=service.evidence_root(current_app.config),
    )
    flash(reason if reason else
          f"Uploaded as version {service.list_for_control(control_id)[0]['version_no']}, "
          f"awaiting review.",
          "danger" if reason else "success")
    return redirect(url_for("evidence.for_control", control_id=control_id))


@bp.route("/<int:evidence_id>/review", methods=["POST"])
@requires("evidence.review")
def review(evidence_id):
    control_id = request.form.get("control_id", type=int)
    ok, message = service.review_evidence(
        evidence_id=evidence_id,
        reviewer_id=current_user()["user_id"],
        decision=request.form.get("decision", ""),
        note=request.form.get("note", ""),
    )
    flash(message, "success" if ok else "danger")
    return redirect(url_for("evidence.for_control", control_id=control_id))
