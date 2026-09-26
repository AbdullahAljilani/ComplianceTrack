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

| Module | State at `v0.3.1-testing-complete` |
|---|---|
| Authentication and Authorization | Implemented. Argon2id hashing, server-side role checks on every protected route, CSRF protection, session hardening. |
| Audit Logging | Implemented. Sign-in, sign-out, control status changes, evidence uploads and reviews, remediation changes. |
| Control Register | Implemented. All 108 ECC-2:2024 main controls, filtering, search, pagination, status workflow with the evidence gate enforced. |
| Evidence Management | Implemented in Unit 5. Upload with an extension allowlist and size cap, SHA-256 integrity digest, duplicate detection, per-control version chain, reviewer approval with separation of duties. |
| Remediation Tracker | Implemented in Unit 5. Findings with owner, priority and due date; derived overdue state; priority-ordered work list; accountable closure. |
| Reporting Dashboard | Implemented. Now reads the scoring service rather than counting for itself. |
| Compliance scoring | Implemented in Unit 5. Weighted implementation score, evidence coverage, priority-weighted remediation exposure, control review currency. |

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

PostgreSQL 16 and Python 3.11 or later must be installed.

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

createdb -U postgres compliancetrack
psql -U postgres -d compliancetrack -f database/schema.sql
psql -U postgres -d compliancetrack -f database/migrations/001_unit4_scope_tier.sql
psql -U postgres -d compliancetrack -f database/seed_reference_data.sql
psql -U postgres -d compliancetrack -f database/seed_ecc_controls.sql
psql -U postgres -d compliancetrack -f database/migrations/002_unit5_core_logic.sql
psql -U postgres -d compliancetrack -f database/seed_unit5_workflow.sql

cp .env.example .env        # then set DB_PASSWORD and FLASK_SECRET_KEY

python scripts/seed_evidence_demo.py        # synthetic evidence, real digests
python scripts/reconcile_evidence_gate.py   # enforce the gate over seeded rows
python app.py
```

Then open http://127.0.0.1:5000

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
python -m pytest -m "not integration"   # 85 unit tests, no database needed
python -m pytest                        # 124 tests including integration
```

| Suite | Tests | Kind |
|---|---|---|
| `test_scoring.py` | 23 | White-box. Every branch of the scoring calculation, including boundary dates and the guard clauses. |
| `test_evidence_service.py` | 29 | Mixed. White-box on validation and versioning, black-box on secure file handling. |
| `test_remediation_service.py` | 19 | Mixed. Black-box on ordering and closure, white-box on validation. |
| `test_access_control.py` | 14 | Black-box against the Unit 3 role matrix. |
| `test_integration_db.py` | 19 | Integration. Service layer, data layer and database constraints together. |
| `test_web_workflow.py` | 20 | Integration. Routing, templates and authorisation through HTTP. |

The unit tests use a stub in place of the data layer, so they exercise the
logic and nothing else. Anything that genuinely needs PostgreSQL is marked
`integration` and kept separate.

## Repository conventions

Branching, tagging and release model: `docs/BRANCHING.md`.
Continuous integration: `.github/workflows/ci.yml`. CI only, by the decision
recorded in Unit 4; there is no continuous deployment and no production
environment.

## Known limitations

- The Flask development server is used, not a production WSGI server, and
  HTTPS is not configured locally, so `SESSION_COOKIE_SECURE` stays off until
  it is.
- Evidence files are stored on the local filesystem outside the web root. There
  is no object store, no retention policy and no anti-virus scanning.
- Seeded control statuses are synthetic and are not an assessment of any
  organisation.
- Scoring weights are a documented convention chosen for this prototype. They
  are not an NCA scoring method, and no such method is implied.
