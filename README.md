# ComplianceTrack

A centralised GRC compliance-tracking dashboard aligned with the Saudi National
Cybersecurity Authority Essential Cybersecurity Controls, ECC-2:2024.

MSIT 5910 capstone project, University of the People. Abdullah Aljilani.

ComplianceTrack helps authorised users organise cybersecurity controls,
evidence, findings and remediation work in one place instead of across
spreadsheets, email and shared folders. **It does not certify compliance with
ECC-2:2024.** Assessment and audit conclusions remain with qualified personnel.
All data in this repository is synthetic.

## What is implemented

| Module | State at `v0.4.0-integration` |
|---|---|
| Authentication and Authorization | Implemented. Argon2id hashing, server-side role checks on every protected route, object-level ownership check on control changes (Unit 6), CSRF protection, session hardening, role-aware start page (Unit 6). |
| Audit Logging | Implemented. Sign-in, sign-out, control status changes, evidence uploads and reviews, remediation changes and closure verification, report exports. |
| Control Register | Implemented. All 108 ECC-2:2024 main controls, filtering, search, pagination, status workflow with the evidence gate enforced; a Control Owner changes only the controls assigned to them (Unit 6). |
| Evidence Management | Implemented in Unit 5. Upload with an extension allowlist and size cap, SHA-256 integrity digest, duplicate detection, per-control version chain, reviewer approval with separation of duties. Unit 6 made simultaneous uploads safe. |
| Remediation Tracker | Implemented in Unit 5. Findings with owner, priority and due date; derived overdue state; priority-ordered, paged work list. Unit 6: closure is requested by the owner and verified by someone else (FR-7). |
| Reporting Dashboard | Implemented. Reads the scoring service; missing evidence and overdue items by domain (Unit 6); CSV exports and a JSON summary (Unit 6). |
| Compliance scoring | Implemented in Unit 5. Weighted implementation score, evidence coverage, priority-weighted remediation exposure, control review currency. |
| Deployment | Unit 6. `serve.py` serves the application with waitress after checking the configuration; `docs/DEPLOYMENT.md` documents prerequisites, settings, build and release. |
| Evaluation | Unit 6. `scripts/evaluate_system.py` measures the test suite, roles, workflows, accuracy, latency, throughput, memory, upload integrity and scale; method and findings in `docs/EVALUATION.md`, raw results in `docs/evaluation/`. |

## Scope

68 of the 108 main controls are tracked: the whole Cybersecurity Governance
domain, the whole Cybersecurity Resilience domain, the whole Third-Party and
Cloud Computing Cybersecurity domain, and five Cybersecurity Defense
subdomains (Asset Management, Identity and Access Management, Data and
Information Protection, Cryptography, Web Application Security).

The remaining 40 are held as catalogue entries so the register reflects the
complete framework. A database constraint fixes them at `Not Yet In Scope`, and
they are excluded from every score, so the interface can never present a
reference entry as an assessed control.

Control text is taken from the official NCA publication.

## Running it

PostgreSQL 16 and Python 3.12 must be installed (3.11 or later on Linux; on
Windows 3.12, because `psycopg2-binary==2.9.9` has no Windows wheel for 3.13).
The full, tested sequence for Windows and Linux is in `docs/DEPLOYMENT.md`. In
short, on Linux:

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: see docs/DEPLOYMENT.md
pip install -r requirements.txt

createdb -U postgres compliancetrack
grep -v '^#' database/load_order.txt | sed '/^$/d' | while read -r f; do
  psql -U postgres -d compliancetrack -v ON_ERROR_STOP=1 -f "database/$f"; done

cp .env.example .env        # then set DB_PASSWORD and FLASK_SECRET_KEY

python scripts/seed_evidence_demo.py        # synthetic evidence, real digests
python scripts/reconcile_evidence_gate.py   # enforce the gate over seeded rows
python app.py                               # development server, port 5000
APP_ENV=demo python serve.py                # waitress, port 8080
```

`database/load_order.txt` lists the SQL files in build order. Unit 6 added
`migrations/003_unit6_closure_verification.sql` to the end of it.

### Demonstration accounts

Synthetic. Password for every account: `ChangeMe#2026`.

| Username | Role |
|---|---|
| `Abdullah.Aljilani` | GRC Administrator |
| `ControlOwner01`, `ControlOwner02` | Control Owner |
| `Custodian01` | Evidence Custodian |
| `Auditor01` | Internal Auditor |
| `Manager01` | Management |

Unit 4 seeded invented personal names. Unit 5 replaced them with the project
owner's own account plus neutral role labels, so the prototype contains no
invented personal data. This is recorded as a refinement in
`database/seed_reference_data.sql`, not a silent change.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -m "not integration"   # 152 unit tests, no database needed
python -m pytest                        # 223 tests including integration
```

| Suite | Tests | Kind |
|---|---|---|
| `test_scoring.py` | 24 | White-box. Every branch of the scoring calculation, including boundary dates and the guard clauses. |
| `test_evidence_service.py` | 31 | Mixed. White-box on validation and versioning, black-box on secure file handling and stored names. |
| `test_remediation_service.py` | 38 | Mixed. Black-box on ordering, closure requests and independent verification; white-box on validation and paging. |
| `test_access_control.py` | 30 | Black-box against the Unit 3 role matrix and the FR-1 ownership rule. |
| `test_reporting_export.py` | 14 | Mixed. CSV building and formula-injection handling. |
| `test_deployment_config.py` | 15 | Black-box. What stops `serve.py` and what only warns. |
| `test_integration_db.py` | 28 | Integration. Service layer, data layer and database constraints together. |
| `test_web_workflow.py` | 43 | Integration. Routing, templates, authorisation and exports through HTTP. |

The unit tests use a stub in place of the data layer, so they exercise the
logic and nothing else. Anything that genuinely needs PostgreSQL is marked
`integration` and kept separate.

## Repository conventions

Branching, tagging and release model: `docs/BRANCHING.md`.
Continuous integration: `.github/workflows/ci.yml`. CI only, by the decision
recorded in Unit 4; there is no continuous deployment and no production
environment. Tool versions are pinned in `requirements-dev.txt` and the lint
rule set in `ruff.toml`, so a CI run gives the same verdict whenever it runs.

## Known limitations

- HTTPS is not configured locally. `serve.py` refuses `APP_ENV=production`
  until `SESSION_COOKIE_SECURE` is on, which assumes a TLS-terminating reverse
  proxy that this repository documents but does not provide.
- Evidence files are stored on the local filesystem outside the web root. There
  is no object store, no retention policy and no anti-virus scanning.
- The tracker pages its list, but it still reads and orders every item on each
  request; ordering in SQL would be needed far beyond the prototype's volume.
- Usability has been evaluated by heuristic review and scripted workflows, not
  yet with real users.
- Seeded control statuses are synthetic and are not an assessment of any
  organisation.
- Scoring weights are a documented convention chosen for this prototype. They
  are not an NCA scoring method, and no such method is implied.
