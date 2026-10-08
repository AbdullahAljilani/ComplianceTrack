"""Exportable compliance summaries.

Unit 2 listed "an export function summarizing compliance by domain" in scope,
and Table 2 of the Unit 3 design names "an exportable compliance summary by
domain" as a Reporting Dashboard output. Units 4 and 5 did not build it; the
Unit 6 feature-completion review did.

The functions here build rows only. They read no request and no database, so
they can be tested in isolation, and the routes that call them decide who may
download what. Every file opens with the same boundary statement the dashboard
carries, because a spreadsheet travels further than a web page does.
"""
import csv
import io

BOUNDARY = ("Tracking information only. ComplianceTrack does not certify "
            "compliance with NCA ECC-2:2024; assessment and audit conclusions "
            "remain with qualified personnel.")

DOMAIN_HEADER = ["Domain", "Tracked controls", "Assessed", "Excluded",
                 "Catalogue only", "Weighted score (%)", "Approved evidence",
                 "Missing evidence", "Open remediation", "Overdue remediation",
                 "Exposure index"]

CONTROL_HEADER = ["ECC reference", "Domain", "Subdomain", "Owner", "Status",
                  "Review date", "Approved evidence", "Pending evidence",
                  "Open remediation", "Overdue remediation"]

# A spreadsheet treats a cell beginning with one of these as a formula. Text a
# user typed must never be able to run as one when the file is opened, so such
# a cell is written with a leading apostrophe (OWASP, CSV injection).
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value):
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def domain_rows(summary, catalogue_by_domain):
    """One row per tracked domain, weakest first, then a total row."""
    gaps = summary.get("domain_gaps", {})
    rows, totals = [], [0] * 9
    for d in summary["by_domain"]:
        g = gaps.get(d["domain"], {})
        values = [d["assessed"] + d["excluded"], d["assessed"], d["excluded"],
                  catalogue_by_domain.get(d["domain"], 0)]
        tail = [g.get("evidenced", 0), g.get("missing_evidence", 0),
                g.get("open", 0), g.get("overdue", 0), g.get("exposure_index", 0)]
        rows.append([d["domain"], *values, d["score"], *tail])
        for i, v in enumerate(values + tail):
            totals[i] += v
    rows.append(["All tracked domains", *totals[:4], summary["implementation"]["score"],
                 *totals[4:]])
    return rows


def render_csv(title, generated, header, rows):
    """Write the preamble, the header and the rows as CSV text."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    for line in (f"# {title}", f"# {generated}", f"# {BOUNDARY}"):
        buffer.write(line + "\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([csv_safe(v) for v in row])
    return buffer.getvalue()
