"""ComplianceTrack system evaluation (Unit 6).

Measures the integrated prototype the way a user reaches it: over HTTP, through
the waitress WSGI server, against a database built from the repository's own
SQL files. Every figure in the Unit 6 report can be regenerated with one
command, and the raw numbers are written to disk rather than copied by hand.

    python scripts/evaluate_system.py --label v0.4.0

Sections
  tests        the pytest suite with statement and branch coverage
  roles        each seeded account signs in and lands on a page it may use
  workflows    five end-to-end workflows driven through the HTTP interface
  accuracy     every dashboard figure checked against an independent SQL oracle
  latency      p50 / p95 / max response time per page, one user
  throughput   requests per second and error rate at 1, 5, 10 and 20 users,
               repeated three times with the median reported
  memory       resident memory of the server process, idle and under load
  integrity    simultaneous uploads to one control: errors and digest mismatches
  scale        dashboard and tracker latency as remediation volume grows

The evaluation builds its own databases (compliancetrack_eval and
compliancetrack_scale) and its own evidence folder, so the demonstration
database is never touched. Nothing here certifies compliance with NCA
ECC-2:2024. The figures describe the software, not any organisation.

Needs the development dependencies: pip install -r requirements-dev.txt
"""
import argparse
import csv
import hashlib
import io
import json
import math
import os
import platform
import re
import secrets
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import psutil
import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

PASSWORD = "ChangeMe#2026"
ACCOUNTS = ["Abdullah.Aljilani", "ControlOwner01", "ControlOwner02",
            "Custodian01", "Auditor01", "Manager01"]
FALLBACK_LOAD_ORDER = [
    "schema.sql",
    "migrations/001_unit4_scope_tier.sql",
    "seed_reference_data.sql",
    "seed_ecc_controls.sql",
    "migrations/002_unit5_core_logic.sql",
    "seed_unit5_workflow.sql",
]
STATUS_WEIGHTS = {"Implemented": 1.0, "Partially Implemented": 0.5,
                  "Evidence Missing": 0.25, "Not Implemented": 0.0}
PRIORITY_WEIGHTS = {"Low": 1, "Medium": 2, "High": 4, "Critical": 8}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def pct(values, q):
    """Nearest-rank percentile, in milliseconds, from a list of seconds."""
    if not values:
        return None
    ordered = sorted(values)
    k = min(len(ordered) - 1, max(0, math.ceil(q / 100 * len(ordered)) - 1))
    return round(ordered[k] * 1000, 1)


def summarise(samples):
    return {
        "n": len(samples),
        "mean_ms": round(statistics.fmean(samples) * 1000, 1) if samples else None,
        "p50_ms": pct(samples, 50),
        "p95_ms": pct(samples, 95),
        "p99_ms": pct(samples, 99),
        "max_ms": round(max(samples) * 1000, 1) if samples else None,
    }


def log(msg):
    print(msg, flush=True)


class Server:
    """Runs the application under waitress in a child process."""

    def __init__(self, repo, env, port, threads):
        self.repo, self.env, self.port, self.threads = repo, env, port, threads
        self.proc = None

    @property
    def base(self):
        return f"http://127.0.0.1:{self.port}"

    def start(self):
        cmd = [sys.executable, "-m", "waitress", f"--listen=127.0.0.1:{self.port}",
               f"--threads={self.threads}", "app:app"]
        self.proc = subprocess.Popen(cmd, cwd=self.repo, env=self.env,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        deadline = time.time() + 40
        while time.time() < deadline:
            try:
                if requests.get(self.base + "/login", timeout=2).status_code == 200:
                    return self
            except requests.RequestException:
                pass
            time.sleep(0.3)
        raise SystemExit("The server did not become ready within 40 seconds.")

    def rss_mb(self):
        return round(psutil.Process(self.proc.pid).memory_info().rss / 1048576, 1)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def csrf_from(html):
    found = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return found.group(1) if found else None


def sign_in(base, username):
    s = requests.Session()
    token = csrf_from(s.get(base + "/login", timeout=10).text)
    r = s.post(base + "/login", data={"username": username, "password": PASSWORD,
                                      "csrf_token": token},
               allow_redirects=False, timeout=10)
    if r.status_code != 302:
        raise RuntimeError(f"sign-in failed for {username}: HTTP {r.status_code}")
    s.landing = r.headers.get("Location", "/")
    return s


def flash_of(html):
    found = re.search(r'class="flash f-(\w+)">([^<]+)<', html)
    return (found.group(1), found.group(2).strip()) if found else (None, None)


# ---------------------------------------------------------------------------
# Database build
# ---------------------------------------------------------------------------

def db_settings(name=None):
    return {"host": os.environ.get("DB_HOST", "localhost"),
            "port": os.environ.get("DB_PORT", "5432"),
            "user": os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD", ""),
            "dbname": name or os.environ.get("DB_NAME", "compliancetrack")}


def recreate_database(name, template=None):
    admin = psycopg2.connect(**db_settings("postgres"))
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        if template:
            cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()", (template,))
            cur.execute(f'CREATE DATABASE "{name}" TEMPLATE "{template}"')
        else:
            cur.execute(f'CREATE DATABASE "{name}"')
    admin.close()


def drop_database(name):
    admin = psycopg2.connect(**db_settings("postgres"))
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    admin.close()


def load_order(repo):
    listed = repo / "database" / "load_order.txt"
    if listed.exists():
        return [ln.strip() for ln in listed.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.lstrip().startswith("#")]
    return FALLBACK_LOAD_ORDER


def build_database(repo, name, env):
    recreate_database(name)
    conn = psycopg2.connect(**db_settings(name))
    conn.autocommit = True
    files = load_order(repo)
    with conn.cursor() as cur:
        for rel in files:
            cur.execute((repo / "database" / rel).read_text(encoding="utf-8"))
    conn.close()
    for script in ("seed_evidence_demo.py", "reconcile_evidence_gate.py"):
        subprocess.run([sys.executable, str(repo / "scripts" / script)], cwd=repo,
                       env=env, check=True, stdout=subprocess.DEVNULL)
    return files


# ---------------------------------------------------------------------------
# Section: tests
# ---------------------------------------------------------------------------

def section_tests(repo, env, workdir):
    """Run the whole pytest suite under coverage against the evaluation
    database, before any other section has written to it."""
    junit, cov_json = workdir / "junit.xml", workdir / "coverage.json"
    sources = ",".join(s for s in ("src", "app", "config", "serve")
                       if (repo / s).exists() or (repo / f"{s}.py").exists())
    t0 = time.perf_counter()
    run = subprocess.run([sys.executable, "-m", "coverage", "run", "--branch",
                          f"--source={sources}", "-m", "pytest", "-q",
                          "-p", "no:cacheprovider", "-o", "addopts=",
                          f"--junitxml={junit}"],
                         cwd=repo, env=env, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    subprocess.run([sys.executable, "-m", "coverage", "json", "-q", "-o", str(cov_json)],
                   cwd=repo, env=env, capture_output=True, text=True)
    import xml.etree.ElementTree as ET
    suite = ET.parse(junit).getroot()
    suite = suite if suite.tag == "testsuite" else suite.find("testsuite")
    total = int(suite.get("tests"))
    failed = int(suite.get("failures")) + int(suite.get("errors"))
    skipped = int(suite.get("skipped", 0))
    totals = json.loads(cov_json.read_text())["totals"]
    for leftover in (repo / ".coverage",):
        if leftover.exists():
            leftover.unlink()
    return {"total": total, "passed": total - failed - skipped, "failed": failed,
            "skipped": skipped, "pytest_seconds": round(float(suite.get("time")), 2),
            "wall_seconds": round(wall, 2),
            "coverage_percent": round(totals["percent_covered"], 1),
            "statements": totals["num_statements"],
            "statements_covered": totals["covered_lines"],
            "branches": totals.get("num_branches"),
            "branches_covered": totals.get("covered_branches"),
            "exit_code": run.returncode}


# ---------------------------------------------------------------------------
# Section: roles
# ---------------------------------------------------------------------------

def section_roles(base):
    out = []
    for user in ACCOUNTS:
        s = sign_in(base, user)
        landing = s.landing
        r = s.get(base + landing if landing.startswith("/") else landing, timeout=10)
        out.append({"account": user, "landing": landing, "status": r.status_code})
    return {"accounts": out,
            "landed_ok": sum(1 for o in out if o["status"] == 200),
            "total": len(out)}


# ---------------------------------------------------------------------------
# Section: workflows
# ---------------------------------------------------------------------------

def _control(conn, where, params=()):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"""SELECT c.control_id, c.ecc_reference, c.status,
                               u.username AS owner
                        FROM controls c LEFT JOIN users u ON u.user_id = c.owner_user_id
                        WHERE {where}
                        ORDER BY string_to_array(c.ecc_reference, '-')::int[]
                        LIMIT 1""", params)
        return cur.fetchone()


def _one(conn, sql, params=()):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def wf_evidence_to_implemented(base, conn):
    """Custodian files evidence, the auditor approves it, the owner records
    the control as Implemented, and the dashboard reflects it."""
    steps = []
    ctl = _control(conn, "c.scope_tier = 'in_scope' AND c.status = 'Partially Implemented' "
                         "AND u.username = 'ControlOwner01' AND NOT EXISTS "
                         "(SELECT 1 FROM evidence e WHERE e.control_id = c.control_id)")
    cid = ctl["control_id"]
    before = _one(conn, "SELECT COUNT(*) AS n FROM controls WHERE status = 'Implemented'")["n"]

    cust = sign_in(base, "Custodian01")
    page = cust.get(f"{base}/evidence/control/{cid}", timeout=10)
    steps.append("Custodian opens the control's evidence page")
    r = cust.post(f"{base}/evidence/control/{cid}/upload",
                  data={"csrf_token": csrf_from(page.text),
                        "description": "Workflow W1 supporting document"},
                  files={"document": ("w1-procedure.pdf", b"%PDF-1.4 W1 " + secrets.token_bytes(64),
                                      "application/pdf")}, timeout=10)
    steps.append("Custodian uploads the document")
    ev = _one(conn, "SELECT evidence_id FROM evidence WHERE control_id = %s "
                    "ORDER BY version_no DESC LIMIT 1", (cid,))
    if ev is None:
        return {"passed": False, "steps": steps, "detail": f"upload refused: {flash_of(r.text)}"}

    aud = sign_in(base, "Auditor01")
    page = aud.get(f"{base}/evidence/control/{cid}", timeout=10)
    steps.append("Auditor opens the evidence page")
    aud.post(f"{base}/evidence/{ev['evidence_id']}/review",
             data={"csrf_token": csrf_from(page.text), "control_id": cid,
                   "decision": "approve", "note": "Checked against the requirement."},
             timeout=10)
    steps.append("Auditor approves the document")

    own = sign_in(base, ctl["owner"])
    page = own.get(f"{base}/controls/{cid}", timeout=10)
    steps.append("Owner opens the control")
    r = own.post(f"{base}/controls/{cid}/status",
                 data={"csrf_token": csrf_from(page.text), "status": "Implemented"},
                 timeout=10)
    steps.append("Owner records the control as Implemented")
    after_status = _one(conn, "SELECT status FROM controls WHERE control_id = %s", (cid,))["status"]
    after = _one(conn, "SELECT COUNT(*) AS n FROM controls WHERE status = 'Implemented'")["n"]
    dash = own.get(base + "/", timeout=10)
    passed = after_status == "Implemented" and after == before + 1 and dash.status_code in (200, 403)
    return {"passed": passed, "steps": steps, "control": ctl["ecc_reference"],
            "detail": f"{ctl['ecc_reference']}: {ctl['status']} -> {after_status}; "
                      f"Implemented controls {before} -> {after}"}


def wf_finding_to_verified_closure(base, conn):
    """The auditor raises a finding, the owner works it and asks for closure,
    and someone other than the owner verifies the closure (FR-7)."""
    steps = []
    ctl = _control(conn, "c.scope_tier = 'in_scope' AND u.username = 'ControlOwner01'")
    owner_id = _one(conn, "SELECT user_id FROM users WHERE username = 'ControlOwner01'")["user_id"]
    aud = sign_in(base, "Auditor01")
    page = aud.get(base + "/remediation/new", timeout=10)
    steps.append("Auditor opens the new-finding form")
    due = (date.today() + timedelta(days=10)).isoformat()
    aud.post(base + "/remediation/new",
             data={"csrf_token": csrf_from(page.text), "control_id": ctl["control_id"],
                   "finding": "Workflow W2: quarterly access review not evidenced.",
                   "owner_user_id": owner_id, "priority": "High", "due_date": due},
             timeout=10)
    steps.append("Auditor raises the finding")
    item = _one(conn, "SELECT remediation_id FROM remediation_items WHERE finding LIKE "
                      "'Workflow W2:%%' ORDER BY remediation_id DESC LIMIT 1")
    rid = item["remediation_id"]

    own = sign_in(base, "ControlOwner01")
    page = own.get(base + "/remediation/", timeout=10)
    steps.append("Owner opens the tracker")
    own.post(f"{base}/remediation/{rid}/status",
             data={"csrf_token": csrf_from(page.text), "status": "In Progress"}, timeout=10)
    steps.append("Owner starts the work")
    page = own.get(base + "/remediation/", timeout=10)
    note = "Access review completed and signed off; evidence filed."
    probe = own.post(f"{base}/remediation/{rid}/request-closure",
                     data={"csrf_token": csrf_from(page.text), "note": note}, timeout=10)
    if probe.status_code == 404:
        # Unit 5 behaviour: the owner closes the item directly.
        page = own.get(base + "/remediation/", timeout=10)
        own.post(f"{base}/remediation/{rid}/close",
                 data={"csrf_token": csrf_from(page.text), "note": note}, timeout=10)
        steps.append("Owner closes the item")
        row = _one(conn, "SELECT status, closed_by FROM remediation_items "
                         "WHERE remediation_id = %s", (rid,))
        independent = row["closed_by"] not in (None, owner_id)
        return {"passed": row["status"] == "Closed" and independent, "steps": steps,
                "fr7_independent_verification": independent,
                "detail": f"item {rid} {row['status']}; closed by the owner, so no "
                          f"independent verification took place"}
    steps.append("Owner requests closure with a note")
    pending = _one(conn, "SELECT status FROM remediation_items WHERE remediation_id = %s",
                   (rid,))["status"]
    # The owner must not be able to verify their own closure.
    page = own.get(base + "/remediation/", timeout=10)
    self_verify = own.post(f"{base}/remediation/{rid}/verify",
                           data={"csrf_token": csrf_from(page.text), "decision": "approve",
                                 "note": "Self approval attempt."}, timeout=10)
    blocked = _one(conn, "SELECT status FROM remediation_items WHERE remediation_id = %s",
                   (rid,))["status"] == pending
    page = aud.get(base + "/remediation/", timeout=10)
    steps.append("Auditor opens the tracker")
    aud.post(f"{base}/remediation/{rid}/verify",
             data={"csrf_token": csrf_from(page.text), "decision": "approve",
                   "note": "Sign-off sighted in the evidence register."}, timeout=10)
    steps.append("Auditor verifies the closure")
    row = _one(conn, "SELECT status, closed_by FROM remediation_items "
                     "WHERE remediation_id = %s", (rid,))
    independent = row["closed_by"] not in (None, owner_id)
    return {"passed": row["status"] == "Closed" and independent and blocked,
            "steps": steps, "fr7_independent_verification": independent,
            "owner_self_verification_blocked": blocked,
            "self_verify_http": self_verify.status_code,
            "detail": f"item {rid}: Open -> In Progress -> {pending} -> {row['status']}"}


def wf_export_for_audit(base, conn):
    """Management exports the compliance summary to answer an audit request."""
    steps = []
    mgr = sign_in(base, "Manager01")
    mgr.get(base + "/", timeout=10)
    steps.append("Manager opens the dashboard")
    r = mgr.get(base + "/reports/domain-summary.csv", timeout=10)
    steps.append("Manager downloads the domain summary")
    if r.status_code == 404:
        return {"passed": False, "steps": steps,
                "detail": "no export function in this version (Unit 2 scope, Unit 3 Table 2)"}
    rows = list(csv.reader(io.StringIO(r.text)))
    r2 = mgr.get(base + "/reports/controls.csv", timeout=10)
    steps.append("Manager downloads the control extract")
    body = list(csv.DictReader(io.StringIO(
        "\n".join(ln for ln in r2.text.splitlines() if not ln.startswith("#")))))
    in_scope = _one(conn, "SELECT COUNT(*) AS n FROM controls WHERE scope_tier = 'in_scope'")["n"]
    boundary = "does not certify" in r.text and "does not certify" in r2.text
    return {"passed": r.status_code == 200 and r2.status_code == 200 and len(body) == in_scope
                      and boundary,
            "steps": steps,
            "detail": f"domain summary {len(rows)} lines; control extract {len(body)} rows "
                      f"for {in_scope} tracked controls; boundary statement present: {boundary}"}


def wf_gate_refusal(base, conn):
    """An owner tries to record Implemented with no approved evidence."""
    steps = []
    ctl = _control(conn, "c.scope_tier = 'in_scope' AND c.status = 'Not Implemented' "
                         "AND u.username = 'ControlOwner02' AND NOT EXISTS "
                         "(SELECT 1 FROM evidence e WHERE e.control_id = c.control_id "
                         "AND e.status = 'Approved')")
    own = sign_in(base, ctl["owner"])
    page = own.get(f"{base}/controls/{ctl['control_id']}", timeout=10)
    steps.append("Owner opens the control")
    r = own.post(f"{base}/controls/{ctl['control_id']}/status",
                 data={"csrf_token": csrf_from(page.text), "status": "Implemented"},
                 timeout=10)
    steps.append("Owner tries to record Implemented")
    status = _one(conn, "SELECT status FROM controls WHERE control_id = %s",
                  (ctl["control_id"],))["status"]
    kind, message = flash_of(r.text)
    return {"passed": status == ctl["status"] and kind == "danger", "steps": steps,
            "detail": f"{ctl['ecc_reference']} stayed {status}; message: {message}"}


def wf_ownership_boundary(base, conn):
    """A Control Owner tries to change a control assigned to someone else."""
    steps = []
    ctl = _control(conn, "c.scope_tier = 'in_scope' AND c.status = 'Not Implemented' "
                         "AND u.username = 'ControlOwner02'")
    other = sign_in(base, "ControlOwner01")
    page = other.get(f"{base}/controls/{ctl['control_id']}", timeout=10)
    steps.append("ControlOwner01 opens a control owned by ControlOwner02")
    token = csrf_from(page.text) or csrf_from(other.get(base + "/controls/", timeout=10).text)
    r = other.post(f"{base}/controls/{ctl['control_id']}/status",
                   data={"csrf_token": token, "status": "Partially Implemented"},
                   timeout=10)
    steps.append("ControlOwner01 submits a status change")
    status = _one(conn, "SELECT status FROM controls WHERE control_id = %s",
                  (ctl["control_id"],))["status"]
    refused = status == ctl["status"]
    return {"passed": refused, "steps": steps, "http": r.status_code,
            "detail": f"{ctl['ecc_reference']} owned by ControlOwner02: "
                      f"{ctl['status']} -> {status} ({'refused' if refused else 'changed'})"}


WORKFLOWS = [
    ("W1", "Evidence filed, independently approved, control recorded as Implemented",
     wf_evidence_to_implemented),
    ("W2", "Finding raised, worked, closure verified by someone other than the owner",
     wf_finding_to_verified_closure),
    ("W3", "Compliance summary exported for an audit request", wf_export_for_audit),
    ("W4", "Implemented refused while no approved evidence exists", wf_gate_refusal),
    ("W5", "Owner refused a change to a control assigned to someone else",
     wf_ownership_boundary),
]


def section_workflows(base):
    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    out = []
    for code, title, fn in WORKFLOWS:
        try:
            result = fn(base, conn)
        except Exception as exc:  # report the failure, keep evaluating
            result = {"passed": False, "steps": [], "detail": f"error: {exc!r}"}
        result.update({"id": code, "title": title, "interactions": len(result["steps"])})
        out.append(result)
        log(f"    {code} {'PASS' if result['passed'] else 'FAIL'}  {result['detail']}")
    conn.close()
    return {"workflows": out, "passed": sum(1 for w in out if w["passed"]),
            "total": len(out)}


# ---------------------------------------------------------------------------
# Section: accuracy
# ---------------------------------------------------------------------------

ORACLE_SQL = {
    "assessed": """SELECT COUNT(*) FROM controls WHERE scope_tier = 'in_scope'
                   AND status NOT IN ('Not Applicable', 'Not Yet In Scope')""",
    "excluded": """SELECT COUNT(*) FROM controls WHERE scope_tier = 'in_scope'
                   AND status IN ('Not Applicable', 'Not Yet In Scope')""",
    "weighted_total": """SELECT COALESCE(SUM(CASE status
                           WHEN 'Implemented' THEN 1.0 WHEN 'Partially Implemented' THEN 0.5
                           WHEN 'Evidence Missing' THEN 0.25 ELSE 0 END), 0)
                         FROM controls WHERE scope_tier = 'in_scope'
                         AND status NOT IN ('Not Applicable', 'Not Yet In Scope')""",
    "evidenced": """SELECT COUNT(*) FROM controls c WHERE c.scope_tier = 'in_scope'
                    AND c.status NOT IN ('Not Applicable', 'Not Yet In Scope')
                    AND EXISTS (SELECT 1 FROM evidence e WHERE e.control_id = c.control_id
                                AND e.status = 'Approved')""",
    "open": "SELECT COUNT(*) FROM remediation_items WHERE status <> 'Closed'",
    "overdue": """SELECT COUNT(*) FROM remediation_items
                  WHERE status <> 'Closed' AND due_date < CURRENT_DATE""",
    "due_soon": """SELECT COUNT(*) FROM remediation_items WHERE status <> 'Closed'
                   AND due_date >= CURRENT_DATE AND due_date <= CURRENT_DATE + 14""",
    "exposure_index": """SELECT COALESCE(SUM(CASE priority WHEN 'Low' THEN 1
                           WHEN 'Medium' THEN 2 WHEN 'High' THEN 4 WHEN 'Critical' THEN 8 END), 0)
                         FROM remediation_items
                         WHERE status <> 'Closed' AND due_date < CURRENT_DATE""",
    "max_days_overdue": """SELECT COALESCE(MAX(CURRENT_DATE - due_date), 0)
                           FROM remediation_items
                           WHERE status <> 'Closed' AND due_date < CURRENT_DATE""",
    "due_review": """SELECT COUNT(*) FROM controls WHERE scope_tier = 'in_scope'
                     AND review_date IS NOT NULL AND review_date < CURRENT_DATE""",
}


def oracle(conn):
    vals = {}
    with conn.cursor() as cur:
        for key, sql in ORACLE_SQL.items():
            cur.execute(sql)
            vals[key] = float(cur.fetchone()[0])
        cur.execute("""SELECT domain,
                         COUNT(*) FILTER (WHERE status NOT IN ('Not Applicable','Not Yet In Scope')),
                         COALESCE(SUM(CASE status WHEN 'Implemented' THEN 1.0
                           WHEN 'Partially Implemented' THEN 0.5
                           WHEN 'Evidence Missing' THEN 0.25 ELSE 0 END)
                           FILTER (WHERE status NOT IN ('Not Applicable','Not Yet In Scope')), 0)
                       FROM controls WHERE scope_tier = 'in_scope' GROUP BY domain""")
        vals["by_domain"] = {d: round(float(w) / a * 100, 1) if a else 0.0
                             for d, a, w in cur.fetchall()}
    vals["score"] = round(vals["weighted_total"] / vals["assessed"] * 100, 1) \
        if vals["assessed"] else 0.0
    vals["coverage"] = round(vals["evidenced"] / vals["assessed"] * 100, 1) \
        if vals["assessed"] else 0.0
    return vals


def _num(text):
    return float(re.sub(r"[^0-9.]", "", text))


def section_accuracy(base, repo):
    checks = []

    def check(name, expected, actual):
        ok = actual is not None and abs(float(expected) - float(actual)) < 1e-6
        checks.append({"check": name, "expected": expected, "actual": actual, "match": ok})

    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    truth = oracle(conn)

    # 1. The scoring service, called in-process exactly as the dashboard calls it.
    sys.path.insert(0, str(repo))
    from app import create_app  # imported here, after the environment is set
    from src.remediation_tracker import service as remediation_service
    from src.services import scoring
    app = create_app()
    with app.app_context():
        s = scoring.dashboard_summary()
        items = remediation_service.list_items()
    imp, ev, rem = s["implementation"], s["evidence"], s["remediation"]
    for key in ("assessed", "excluded", "weighted_total", "score"):
        check(f"service.implementation.{key}", truth[key], imp[key])
    check("service.evidence.evidenced", truth["evidenced"], ev["evidenced"])
    check("service.evidence.percent", truth["coverage"], ev["percent"])
    for key in ("open", "overdue", "due_soon", "exposure_index", "max_days_overdue"):
        check(f"service.remediation.{key}", truth[key], rem[key])
    check("service.due_review", truth["due_review"], s["due_review"])
    for d in s["by_domain"]:
        check(f"service.domain[{d['domain']}]", truth["by_domain"][d["domain"]], d["score"])

    # 2. Each tracker row's derived state against the rule stated in Unit 3.
    today = date.today()
    item_ok = 0
    for i in items:
        if i["status"] == "Closed":
            expected = "closed"
        elif i["due_date"] < today:
            expected = "overdue"
        elif (i["due_date"] - today).days <= 14:
            expected = "due_soon"
        else:
            expected = "on_track"
        item_ok += expected == i["derived_state"]
    checks.append({"check": "tracker.derived_state (per item)", "expected": len(items),
                   "actual": item_ok, "match": item_ok == len(items)})

    # 3. The figures a signed-in user actually sees on the dashboard page.
    admin = sign_in(base, "Abdullah.Aljilani")
    html = admin.get(base + "/", timeout=10).text
    tiles = {re.sub(r"\s+", " ", lab).strip(): val.strip() for val, lab in re.findall(
        r'<div class="n">([^<]+)</div>\s*<div class="l">([^<]+)', html)}
    for label, key in (("Weighted implementation score", "score"),
                       ("Evidence coverage", "coverage"),
                       ("Overdue remediation", "overdue"),
                       ("Priority-weighted exposure", "exposure_index")):
        shown = next((v for k, v in tiles.items() if k.startswith(label)), None)
        check(f"page.dashboard.{key}", truth[key], _num(shown) if shown else None)

    # 4. The tracker page and the dashboard agree on what is overdue.
    rhtml = admin.get(base + "/remediation/", timeout=10).text
    rtiles = dict((re.sub(r"\s+", " ", lab).strip(), val) for val, lab in re.findall(
        r'<div class="n">([^<]+)</div>\s*<div class="l">([^<]+)', rhtml))
    check("page.tracker.overdue", truth["overdue"], _num(rtiles.get("Overdue", "nan")))

    # 5. Machine-readable outputs, where this version has them.
    api = admin.get(base + "/api/summary", timeout=10)
    if api.status_code == 200:
        data = api.json()
        check("api.implementation.score", truth["score"], data["implementation"]["score"])
        check("api.evidence.percent", truth["coverage"], data["evidence"]["percent"])
        check("api.remediation.overdue", truth["overdue"], data["remediation"]["overdue"])
        check("api.remediation.exposure_index", truth["exposure_index"],
              data["remediation"]["exposure_index"])
    exp = admin.get(base + "/reports/controls.csv", timeout=10)
    if exp.status_code == 200:
        lines = [ln for ln in exp.text.splitlines() if not ln.startswith("#")]
        rows = list(csv.DictReader(io.StringIO("\n".join(lines))))
        with conn.cursor() as cur:
            cur.execute("SELECT ecc_reference, status FROM controls WHERE scope_tier = 'in_scope'")
            db_status = dict(cur.fetchall())
        agree = sum(1 for r in rows if db_status.get(r["ECC reference"]) == r["Status"])
        checks.append({"check": "export.controls.status (per row)", "expected": len(db_status),
                       "actual": agree, "match": agree == len(db_status) == len(rows)})
    conn.close()
    return {"checks": checks, "matched": sum(1 for c in checks if c["match"]),
            "total": len(checks), "oracle": truth}


# ---------------------------------------------------------------------------
# Section: latency, throughput, memory
# ---------------------------------------------------------------------------

def endpoints(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT control_id FROM controls WHERE ecc_reference = '1-1-1'")
        cid = cur.fetchone()[0]
    return [("Sign-in page", "/login", False),
            ("Dashboard", "/", True),
            ("Control Register", "/controls/", True),
            ("Register search", "/controls/?q=access", True),
            ("Control detail", f"/controls/{cid}", True),
            ("Evidence page", f"/evidence/control/{cid}", True),
            ("Remediation Tracker", "/remediation/", True),
            ("Domain summary export", "/reports/domain-summary.csv", True),
            ("Control extract export", "/reports/controls.csv", True),
            ("Summary API", "/api/summary", True)]


def section_latency(base, n, warmup):
    conn = psycopg2.connect(**db_settings())
    eps = endpoints(conn)
    conn.close()
    admin = sign_in(base, "Abdullah.Aljilani")
    anon = requests.Session()
    out = []
    for name, path, auth in eps:
        s = admin if auth else anon
        first = s.get(base + path, timeout=30)
        if first.status_code == 404:
            out.append({"endpoint": name, "path": path, "available": False})
            continue
        for _ in range(warmup):
            s.get(base + path, timeout=30)
        samples, codes = [], {}
        for _ in range(n):
            t0 = time.perf_counter()
            r = s.get(base + path, timeout=30)
            samples.append(time.perf_counter() - t0)
            codes[r.status_code] = codes.get(r.status_code, 0) + 1
        row = {"endpoint": name, "path": path, "available": True,
               "bytes": len(first.content), "codes": codes}
        row.update(summarise(samples))
        out.append(row)
        log(f"    {name:<24} p50 {row['p50_ms']:>7} ms   p95 {row['p95_ms']:>7} ms")
    return out


class RssSampler(threading.Thread):
    def __init__(self, server, every=0.05):
        super().__init__(daemon=True)
        self.server, self.every, self.peak, self._stop_evt = server, every, 0.0, threading.Event()

    def run(self):
        while not self._stop_evt.is_set():
            try:
                self.peak = max(self.peak, self.server.rss_mb())
            except psutil.Error:
                pass
            time.sleep(self.every)

    def stop(self):
        self._stop_evt.set()
        self.join()


def section_throughput(server, levels, per_level):
    base, out = server.base, []
    sampler = RssSampler(server)
    sampler.start()
    for users in levels:
        sessions = [sign_in(base, "Abdullah.Aljilani") for _ in range(users)]
        per_user = max(1, per_level // users)
        lat, errors, lock = [], [0], threading.Lock()

        def worker(sess):
            local = []
            for _ in range(per_user):
                t0 = time.perf_counter()
                try:
                    ok = sess.get(base + "/", timeout=60).status_code == 200
                except requests.RequestException:
                    ok = False
                local.append(time.perf_counter() - t0)
                if not ok:
                    with lock:
                        errors[0] += 1
            with lock:
                lat.extend(local)

        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=users) as pool:
            list(pool.map(worker, sessions))
        wall = time.perf_counter() - t0
        total = per_user * users
        row = {"users": users, "requests": total, "seconds": round(wall, 2),
               "throughput_rps": round(total / wall, 1),
               "error_rate_pct": round(errors[0] / total * 100, 2)}
        row.update({k: v for k, v in summarise(lat).items() if k != "n"})
        out.append(row)
        log(f"    {users:>2} users  {row['throughput_rps']:>6} req/s  p95 {row['p95_ms']:>7} ms  "
            f"errors {row['error_rate_pct']}%")
    sampler.stop()
    return out, sampler.peak


# ---------------------------------------------------------------------------
# Section: integrity under simultaneous uploads
# ---------------------------------------------------------------------------

def section_integrity(base, evidence_root, pairs):
    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("""SELECT c.control_id FROM controls c WHERE c.scope_tier = 'in_scope'
                       AND NOT EXISTS (SELECT 1 FROM evidence e WHERE e.control_id = c.control_id)
                       ORDER BY c.control_id LIMIT %s""", (pairs,))
        ids = [r[0] for r in cur.fetchall()]
    codes, lock = {}, threading.Lock()

    def upload(sess, token, cid, content, barrier):
        barrier.wait()
        r = sess.post(f"{base}/evidence/control/{cid}/upload",
                      data={"csrf_token": token, "description": "simultaneous upload"},
                      files={"document": ("same-name.txt", content, "text/plain")},
                      allow_redirects=False, timeout=30)
        with lock:
            codes[r.status_code] = codes.get(r.status_code, 0) + 1

    for cid in ids:
        a, b = sign_in(base, "Custodian01"), sign_in(base, "Abdullah.Aljilani")
        ta = csrf_from(a.get(f"{base}/evidence/control/{cid}", timeout=10).text)
        tb = csrf_from(b.get(f"{base}/evidence/control/{cid}", timeout=10).text)
        barrier = threading.Barrier(2)
        threads = [threading.Thread(target=upload, args=(a, ta, cid, f"A-{cid}\n".encode() * 40, barrier)),
                   threading.Thread(target=upload, args=(b, tb, cid, f"B-{cid}\n".encode() * 40, barrier))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    with conn.cursor() as cur:
        cur.execute("SELECT storage_path, sha256_hash FROM evidence WHERE control_id = ANY(%s)",
                    (ids,))
        rows = cur.fetchall()
        cur.execute("SELECT storage_path FROM evidence")
        referenced = {os.path.normpath(p) for (p,) in cur.fetchall()}
    mismatched = 0
    for path, digest in rows:
        try:
            with open(path, "rb") as fh:
                mismatched += hashlib.sha256(fh.read()).hexdigest() != digest.strip()
        except OSError:
            mismatched += 1
    on_disk = [os.path.normpath(os.path.join(evidence_root, f)) for f in os.listdir(evidence_root)]
    orphans = [p for p in on_disk if p not in referenced]
    conn.close()
    errors = sum(v for k, v in codes.items() if k >= 500)
    return {"pairs": len(ids), "requests": 2 * len(ids), "http_codes": codes,
            "server_errors": errors, "records_created": len(rows),
            "digest_mismatches": mismatched, "orphan_files": len(orphans)}


# ---------------------------------------------------------------------------
# Section: scale
# ---------------------------------------------------------------------------

SCALE_INSERT = """
INSERT INTO remediation_items (control_id, finding, owner_user_id, priority, due_date, status)
SELECT c.control_id,
       'Synthetic scale-test finding ' || g,
       (SELECT user_id FROM users WHERE username = CASE WHEN g %% 2 = 0
            THEN 'ControlOwner01' ELSE 'ControlOwner02' END),
       (ARRAY['Low','Medium','High','Critical'])[1 + g %% 4],
       CURRENT_DATE + ((g %% 120) - 60),
       CASE WHEN g %% 3 = 0 THEN 'In Progress' ELSE 'Open' END
FROM generate_series(1, %s) AS g
JOIN LATERAL (SELECT control_id FROM controls WHERE scope_tier = 'in_scope'
              ORDER BY control_id OFFSET (g %% 68) LIMIT 1) c ON true
"""


def section_scale(server_factory, sizes, n_dash, n_tracker):
    out = []
    conn = psycopg2.connect(**db_settings())
    conn.autocommit = True
    server = server_factory().start()
    try:
        admin = sign_in(server.base, "Abdullah.Aljilani")
        current = None
        for target in sizes:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM remediation_items")
                current = cur.fetchone()[0]
                if target > current:
                    cur.execute(SCALE_INSERT, (target - current,))
                cur.execute("ANALYZE remediation_items")
                cur.execute("SELECT COUNT(*) FROM remediation_items")
                current = cur.fetchone()[0]
            row = {"remediation_items": current}
            for label, path, n in (("dashboard", "/", n_dash),
                                   ("tracker", "/remediation/", n_tracker)):
                admin.get(server.base + path, timeout=300)
                samples, size = [], 0
                for _ in range(n):
                    t0 = time.perf_counter()
                    r = admin.get(server.base + path, timeout=300)
                    samples.append(time.perf_counter() - t0)
                    size = len(r.content)
                s = summarise(samples)
                row[f"{label}_p50_ms"], row[f"{label}_p95_ms"] = s["p50_ms"], s["p95_ms"]
                row[f"{label}_kb"] = round(size / 1024, 1)
            row["rss_mb"] = server.rss_mb()
            out.append(row)
            log(f"    {current:>6} items  dashboard p50 {row['dashboard_p50_ms']:>8} ms   "
                f"tracker p50 {row['tracker_p50_ms']:>8} ms ({row['tracker_kb']} KB)")
    finally:
        server.stop()
        conn.close()
    return out


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def markdown_summary(r):
    m = r["meta"]
    lines = [f"# Evaluation {m['label']} ({m['git']})", "",
             f"Run {m['run_at_utc']} on {m['platform']}, Python {m['python']}, "
             f"PostgreSQL {m['postgresql']}, {m['cpu_logical']} logical CPUs, "
             f"{m['memory_gb']} GB. Server: {m['server']}.", "",
             "| Measure | Result |", "|---|---|"]
    if "tests" in r:
        t = r["tests"]
        lines.append(f"| Test suite | {t['passed']} of {t['total']} passed in "
                     f"{t['pytest_seconds']} s; coverage {t['coverage_percent']}% |")
    if "roles" in r:
        lines.append(f"| Accounts landing on a permitted page | {r['roles']['landed_ok']} of "
                     f"{r['roles']['total']} |")
    if "workflows" in r:
        lines.append(f"| Workflows completed as specified | {r['workflows']['passed']} of "
                     f"{r['workflows']['total']} |")
    if "accuracy" in r:
        lines.append(f"| Figures matching the SQL oracle | {r['accuracy']['matched']} of "
                     f"{r['accuracy']['total']} |")
    if "latency" in r:
        worst = max((x for x in r["latency"] if x.get("available")), key=lambda x: x["p95_ms"])
        lines.append(f"| Slowest page, p95, one user | {worst['endpoint']}: {worst['p95_ms']} ms |")
    if "throughput" in r:
        top = r["throughput"][-1]
        lines.append(f"| Dashboard at {top['users']} users | {top['throughput_rps']} req/s, "
                     f"p95 {top['p95_ms']} ms, errors {top['error_rate_pct']}% |")
    if "memory" in r:
        mm = r["memory"]
        lines.append(f"| Server memory (RSS) | idle {mm['idle_mb']} MB, peak "
                     f"{mm['peak_under_load_mb']} MB |")
    if "integrity" in r:
        i = r["integrity"]
        lines.append(f"| Simultaneous uploads ({i['requests']}) | {i['server_errors']} server "
                     f"errors, {i['digest_mismatches']} digest mismatches, "
                     f"{i['orphan_files']} orphan files |")
    if "scale" in r:
        big = r["scale"][-1]
        lines.append(f"| Tracker at {big['remediation_items']} items, p50 | "
                     f"{big['tracker_p50_ms']} ms ({big['tracker_kb']} KB) |")
    if "workflows" in r:
        lines += ["", "| Workflow | Result | Detail |", "|---|---|---|"]
        for w in r["workflows"]["workflows"]:
            lines.append(f"| {w['id']} {w['title']} | {'pass' if w['passed'] else 'fail'} | "
                         f"{w['detail']} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--label", default="local")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--per-level", type=int, default=400)
    parser.add_argument("--repeat", type=int, default=3,
                        help="throughput runs; the median of each level is reported")
    parser.add_argument("--pairs", type=int, default=15)
    parser.add_argument("--scale", default="12,1000,5000,20000")
    parser.add_argument("--skip", default="", help="comma-separated sections to skip")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    load_dotenv(repo / ".env")
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    out_dir = Path(args.out) if args.out else repo / "docs" / "evaluation" / args.label
    out_dir.mkdir(parents=True, exist_ok=True)

    eval_db, scale_db = "compliancetrack_eval", "compliancetrack_scale"
    workdir = Path(tempfile.mkdtemp(prefix="ct-eval-"))
    evidence_root = workdir / "evidence"
    evidence_root.mkdir()
    env = dict(os.environ, DB_NAME=eval_db, EVIDENCE_ROOT=str(evidence_root),
               FLASK_SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32),
               PYTHONIOENCODING="utf-8")
    os.environ.update({k: env[k] for k in ("DB_NAME", "EVIDENCE_ROOT", "FLASK_SECRET_KEY")})

    commit = subprocess.run(["git", "describe", "--tags", "--always", "--dirty"], cwd=repo,
                            capture_output=True, text=True).stdout.strip()
    pg = psycopg2.connect(**db_settings("postgres"))
    with pg.cursor() as cur:
        cur.execute("SHOW server_version")
        pg_version = cur.fetchone()[0]
    pg.close()
    meta = {"label": args.label, "git": commit,
            "run_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "platform": platform.platform(), "python": platform.python_version(),
            "cpu_logical": psutil.cpu_count(), "memory_gb": round(psutil.virtual_memory().total / 1e9, 1),
            "postgresql": pg_version, "server": f"waitress, {args.threads} threads, 127.0.0.1",
            "requests_per_endpoint": args.requests, "warmup": args.warmup}
    log(f"\nComplianceTrack evaluation  [{args.label}]  {commit}")
    log(f"  {meta['platform']} | Python {meta['python']} | PostgreSQL {pg_version} | "
        f"{meta['cpu_logical']} logical CPUs")

    results = {"meta": meta}
    log("\n  Building the evaluation database from the repository's SQL files")
    meta["load_order"] = build_database(repo, eval_db, env)

    if "tests" not in skip:
        log("\n  Test suite, with coverage")
        results["tests"] = section_tests(repo, env, workdir)
        t = results["tests"]
        log(f"    {t['passed']} of {t['total']} passed in {t['pytest_seconds']} s; "
            f"coverage {t['coverage_percent']}% (statements and branches)")

    server = Server(repo, env, args.port, args.threads)
    rss_before = None
    try:
        server.start()
        rss_before = server.rss_mb()
        if "roles" not in skip:
            log("\n  Roles")
            results["roles"] = section_roles(server.base)
            for a in results["roles"]["accounts"]:
                log(f"    {a['account']:<18} -> {a['landing']:<12} HTTP {a['status']}")
        if "accuracy" not in skip:
            log("\n  Accuracy")
            results["accuracy"] = section_accuracy(server.base, repo)
            acc = results["accuracy"]
            log(f"    {acc['matched']} of {acc['total']} checks match the oracle")
        if "latency" not in skip:
            log("\n  Latency, one user")
            results["latency"] = section_latency(server.base, args.requests, args.warmup)
        rss_warm = server.rss_mb()
        if "throughput" not in skip:
            levels, runs, peak = [1, 5, 10, 20], [], rss_warm
            for n in range(args.repeat):
                log(f"\n  Throughput, dashboard (run {n + 1} of {args.repeat})")
                out, run_peak = section_throughput(server, levels, args.per_level)
                runs.append(out)
                peak = max(peak, run_peak)
            results["throughput_runs"] = runs
            results["throughput"] = []
            for i, users in enumerate(levels):
                same = [r[i] for r in runs]
                results["throughput"].append({
                    "users": users, "runs": len(same),
                    "requests": same[0]["requests"],
                    "throughput_rps": statistics.median(x["throughput_rps"] for x in same),
                    "p50_ms": statistics.median(x["p50_ms"] for x in same),
                    "p95_ms": statistics.median(x["p95_ms"] for x in same),
                    "error_rate_pct": max(x["error_rate_pct"] for x in same),
                    "throughput_range": [min(x["throughput_rps"] for x in same),
                                         max(x["throughput_rps"] for x in same)]})
            if args.repeat > 1:
                log("\n  Throughput, median of the runs")
                for row in results["throughput"]:
                    log(f"    {row['users']:>2} users  {row['throughput_rps']:>6} req/s "
                        f"(range {row['throughput_range'][0]} to {row['throughput_range'][1]})"
                        f"  p95 {row['p95_ms']:>7} ms")
        else:
            peak = rss_warm
        results["memory"] = {"idle_mb": rss_before, "after_latency_mb": rss_warm,
                             "peak_under_load_mb": max(peak, rss_warm),
                             "after_load_mb": server.rss_mb()}
        log(f"\n  Memory  idle {rss_before} MB, warm {rss_warm} MB, "
            f"peak {results['memory']['peak_under_load_mb']} MB")
        if "workflows" not in skip:
            log("\n  Workflows")
            results["workflows"] = section_workflows(server.base)
        if "integrity" not in skip:
            log("\n  Integrity, simultaneous uploads")
            results["integrity"] = section_integrity(server.base, str(evidence_root), args.pairs)
            i = results["integrity"]
            log(f"    {i['requests']} uploads: {i['server_errors']} server errors, "
                f"{i['digest_mismatches']} digest mismatches, {i['orphan_files']} orphan files")
    finally:
        server.stop()

    if "scale" not in skip:
        log("\n  Scale, growing remediation volume")
        recreate_database(scale_db, template=eval_db)
        scale_env = dict(env, DB_NAME=scale_db)
        os.environ["DB_NAME"] = scale_db
        sizes = [int(x) for x in args.scale.split(",")]
        results["scale"] = section_scale(
            lambda: Server(repo, scale_env, args.port + 1, args.threads), sizes, 30, 10)
        os.environ["DB_NAME"] = eval_db
        drop_database(scale_db)

    (out_dir / "results.json").write_text(json.dumps(results, indent=2, default=str),
                                          encoding="utf-8")
    (out_dir / "summary.md").write_text(markdown_summary(results), encoding="utf-8")
    if "latency" in results:
        with open(out_dir / "latency.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["endpoint", "path", "n", "mean_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms"])
            for r in results["latency"]:
                if r.get("available"):
                    w.writerow([r["endpoint"], r["path"], r["n"], r["mean_ms"], r["p50_ms"],
                                r["p95_ms"], r["p99_ms"], r["max_ms"]])
    shutil.rmtree(workdir, ignore_errors=True)
    log(f"\n  Results written to {out_dir}\n")


if __name__ == "__main__":
    main()
