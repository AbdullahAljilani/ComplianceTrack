"""Reporting Dashboard module.

Read-only aggregate views over the shared database. Output is explicitly framed
as compliance tracking information, never as a compliance certification, which
is the boundary the project sets for itself.
"""
from flask import Blueprint, render_template

from src import db
from src.services.auth import has_permission, requires

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@requires("report.view")
def index():
    by_status = db.query(
        """
        SELECT status, COUNT(*) AS n
        FROM controls WHERE scope_tier = 'in_scope'
        GROUP BY status ORDER BY n DESC
        """
    )
    by_domain = db.query(
        """
        SELECT domain,
               COUNT(*) FILTER (WHERE scope_tier = 'in_scope')     AS tracked,
               COUNT(*) FILTER (WHERE scope_tier = 'catalog_only') AS catalog,
               COUNT(*) FILTER (WHERE status = 'Implemented')      AS implemented
        FROM controls GROUP BY domain ORDER BY domain
        """
    )
    totals = db.query_one(
        """
        SELECT COUNT(*)                                            AS all_controls,
               COUNT(*) FILTER (WHERE scope_tier = 'in_scope')     AS tracked,
               COUNT(*) FILTER (WHERE scope_tier = 'catalog_only') AS catalog,
               COUNT(*) FILTER (WHERE status = 'Implemented')      AS implemented,
               COUNT(*) FILTER (WHERE status = 'Evidence Missing') AS evidence_missing
        FROM controls
        """
    )
    overdue = db.query_one("SELECT COUNT(*) AS n FROM v_overdue_remediation")["n"]

    audit_recent = []
    if has_permission("audit.view"):
        from src.services import audit as audit_service
        audit_recent = audit_service.recent(8)

    return render_template(
        "dashboard.html", by_status=by_status, by_domain=by_domain,
        totals=totals, overdue=overdue, audit_recent=audit_recent,
    )
