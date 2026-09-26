"""Reporting Dashboard module.

Read-only aggregate views over the shared database. In Unit 4 this module ran
its own counting queries. In Unit 5 the counting has moved into the scoring
service, so the dashboard, the Control Register and any later report all read
the same figures from one place instead of each maintaining its own arithmetic.

Output is explicitly framed as compliance tracking information, never as a
compliance certification, which is the boundary the project sets for itself.
"""
from flask import Blueprint, render_template

from src import db
from src.services import scoring
from src.services.auth import has_permission, requires

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@requires("report.view")
def index():
    summary = scoring.dashboard_summary()

    by_status = db.query(
        """
        SELECT status, COUNT(*) AS n
        FROM controls WHERE scope_tier = 'in_scope'
        GROUP BY status ORDER BY n DESC
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
    catalog_by_domain = {
        r["domain"]: r["n"] for r in db.query(
            "SELECT domain, COUNT(*) AS n FROM controls "
            "WHERE scope_tier = 'catalog_only' GROUP BY domain")
    }

    audit_recent = []
    if has_permission("audit.view"):
        from src.services import audit as audit_service
        audit_recent = audit_service.recent(8)

    return render_template(
        "dashboard.html", summary=summary, by_status=by_status, totals=totals,
        catalog_by_domain=catalog_by_domain, audit_recent=audit_recent,
        weights=scoring.STATUS_WEIGHTS,
    )
