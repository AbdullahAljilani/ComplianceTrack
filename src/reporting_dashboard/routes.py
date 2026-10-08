"""Reporting Dashboard module.

Read-only aggregate views over the shared database. In Unit 4 this module ran
its own counting queries. In Unit 5 the counting moved into the scoring
service, so the dashboard, the Control Register and any later report all read
the same figures from one place instead of each maintaining its own arithmetic.

Unit 6 completes the module against its Unit 3 specification: missing evidence
and overdue remediation are shown by domain (FR-8), and the summary can be
exported as CSV or read as JSON. Each export is the same figures the dashboard
shows, from the same service call, so a downloaded file and the page cannot
disagree.

Output is explicitly framed as compliance tracking information, never as a
compliance certification, which is the boundary the project sets for itself.
"""
from datetime import date, datetime, timezone

from flask import Blueprint, Response, jsonify, render_template

from src import db
from src.reporting_dashboard import export
from src.services import audit, scoring
from src.services.auth import current_user, has_permission, requires

bp = Blueprint("dashboard", __name__)


def _catalogue_by_domain():
    return {
        r["domain"]: r["n"] for r in db.query(
            "SELECT domain, COUNT(*) AS n FROM controls "
            "WHERE scope_tier = 'catalog_only' GROUP BY domain")
    }


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

    audit_recent = []
    if has_permission("audit.view"):
        audit_recent = audit.recent(8)

    return render_template(
        "dashboard.html", summary=summary, by_status=by_status, totals=totals,
        catalog_by_domain=_catalogue_by_domain(), audit_recent=audit_recent,
        weights=scoring.STATUS_WEIGHTS,
    )


def _generated_line():
    user = current_user()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"Generated {stamp} by {user['username']} ({user['role']})"


def _csv_response(text, stem, report):
    # The export leaves the application, so who took it is recorded, and no
    # cache along the way may keep a copy of a page describing weak controls.
    audit.record("REPORT_EXPORT", "report", 0, {"report": report})
    filename = f"{stem}-{date.today().isoformat()}.csv"
    return Response(
        text, mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"',
                 "Cache-Control": "no-store"})


@bp.route("/reports/domain-summary.csv")
@requires("report.view")
def export_domain_summary():
    summary = scoring.dashboard_summary()
    text = export.render_csv(
        "ComplianceTrack compliance tracking summary by domain",
        _generated_line(), export.DOMAIN_HEADER,
        export.domain_rows(summary, _catalogue_by_domain()))
    return _csv_response(text, "compliancetrack-domain-summary", "domain-summary.csv")


@bp.route("/reports/controls.csv")
@requires("report.view")
def export_controls():
    # Overdue is judged against the application's date, the same date the
    # scoring service uses, rather than the database clock.
    rows = db.query(
        """
        SELECT c.ecc_reference, c.domain, c.subdomain,
               COALESCE(u.full_name, 'Unassigned') AS owner, c.status,
               c.review_date,
               cov.approved_count, cov.pending_count,
               (SELECT COUNT(*) FROM remediation_items r
                 WHERE r.control_id = c.control_id AND r.status <> 'Closed') AS open_items,
               (SELECT COUNT(*) FROM remediation_items r
                 WHERE r.control_id = c.control_id AND r.status <> 'Closed'
                   AND r.due_date < %s) AS overdue_items
        FROM controls c
        LEFT JOIN users u ON u.user_id = c.owner_user_id
        JOIN v_control_evidence_coverage cov ON cov.control_id = c.control_id
        WHERE c.scope_tier = 'in_scope'
        ORDER BY string_to_array(c.ecc_reference, '-')::int[]
        """,
        (date.today(),),
    )
    text = export.render_csv(
        "ComplianceTrack control register extract (tracked controls)",
        _generated_line(), export.CONTROL_HEADER,
        [[r["ecc_reference"], r["domain"], r["subdomain"], r["owner"], r["status"],
          r["review_date"].isoformat() if r["review_date"] else "",
          r["approved_count"], r["pending_count"], r["open_items"], r["overdue_items"]]
         for r in rows])
    return _csv_response(text, "compliancetrack-control-extract", "controls.csv")


@bp.route("/api/summary")
@requires("report.view")
def api_summary():
    """The dashboard's figures as JSON, for another tool to read.

    Read-only and session-authenticated like every other route: it adds no
    write path and no new way in.
    """
    payload = scoring.dashboard_summary()
    payload["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload["boundary"] = export.BOUNDARY
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    return response
