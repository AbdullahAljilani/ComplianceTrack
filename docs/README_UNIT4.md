> **Superseded.** This is the Unit 4 README, kept as a record of the state at
> tag `v0.2.0-prototype`. The current README.md describes the Unit 5 state.
> The account names and control counts below were changed in Unit 5; see
> `database/migrations/002_unit5_core_logic.sql` and the current README.

# ComplianceTrack, Unit 4 initial implementation

Working prototype of the Control Register and Reporting Dashboard, built on the
layered architecture and PostgreSQL schema designed in Unit 3.

## What is actually implemented

| Module | State |
|---|---|
| Authentication and Authorization service | Implemented. Argon2id password hashing, server-side role checks on every protected request, CSRF protection, session hardening. |
| Audit Logging service | Implemented. Sign-in, sign-in failure, sign-out and control status changes. |
| Control Register | Implemented. All 108 ECC-2:2024 main controls, filtering, search, pagination, detail view, status update with the Unit 3 evidence rule enforced. |
| Reporting Dashboard | Implemented. Counts by status and domain, overdue remediation count, recent activity. |
| Evidence Management | Designed, not implemented. Tables exist; the rule that depends on approved evidence is already enforced. |
| Remediation Tracker | Designed, not implemented. Tables and the overdue view exist and the dashboard reads the view. |

Control data is taken from the official NCA publication: 4 domains, 28
subdomains, 108 main controls. 56 are tracked by the prototype (the whole
Cybersecurity Governance domain plus Asset Management, Identity and Access
Management, Data and Information Protection, Cryptography, and Web Application
Security). The other 52 are loaded as catalogue reference entries fixed at
`Not Yet In Scope`, which the database enforces with a constraint.

All user data is synthetic. No real organisational data is used.

## Setup on Windows

Run these from the repository root in PowerShell. PostgreSQL 16 and Python 3.11+
must already be installed, and `psql` must be on your PATH.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create the database and load it. You will be prompted for your postgres password
each time.

```powershell
createdb -U postgres compliancetrack
psql -U postgres -d compliancetrack -f database\schema.sql
psql -U postgres -d compliancetrack -f database\migrations\001_unit4_scope_tier.sql
psql -U postgres -d compliancetrack -f database\seed_reference_data.sql
psql -U postgres -d compliancetrack -f database\seed_ecc_controls.sql
```

Create your local configuration. Copy the example and edit the password.

```powershell
Copy-Item .env.example .env
notepad .env
```

Start it.

```powershell
python app.py
```

Then open http://127.0.0.1:5000

## Demonstration accounts

All synthetic, all with the password `ChangeMe#2026`.

| Username | Role | Can do |
|---|---|---|
| `a.rashid` | GRC Administrator | Everything, including the audit trail |
| `m.otaibi` | Control Owner | View and update assigned controls |
| `k.dossari` | Evidence Custodian | View controls and evidence |
| `n.zahrani` | Internal Auditor | View everything, including the audit trail |
| `f.qahtani` | Management | Read-only dashboard and register |

## Verifying it works

With the application running, in a second terminal:

```powershell
pip install requests
python tests\smoke_test.py
```

21 checks covering authentication, authorisation, the register, the status
workflow and CSRF. All 21 passed on the build shipped here.

## How the Unit 3 design shows up in the code

- **Layered architecture.** `app.py` composes the layers; `src/services/`
  holds the two shared services; `src/control_register/` and
  `src/reporting_dashboard/` are the feature modules; `src/db.py` is the only
  path to the data layer.
- **Shared authorisation, not interface hiding.** `@requires("control.edit")`
  runs server-side on every protected route. The Management role is refused the
  status update even when the request is posted directly, not merely hidden from
  the menu.
- **Parameterised queries everywhere.** No SQL string is built by concatenating
  a user-supplied value, including the filter and search conditions.
- **Argon2id**, as the Unit 3 non-functional requirements specify.
- **The evidence rule from Unit 3 Table 2.** A control cannot reach
  `Implemented` until approved evidence exists, enforced in the application
  layer.
- **Derived overdue status.** The dashboard reads `v_overdue_remediation`
  rather than a stored flag, as designed.

## Known limitations

- The development server is used, not a production WSGI server. HTTPS is not
  configured locally, so `SESSION_COOKIE_SECURE` stays off until it is.
- Evidence Management and the Remediation Tracker are not implemented, so the
  evidence count is always zero and no control can currently reach
  `Implemented` through the interface. This is the designed rule behaving
  correctly, not a defect.
- Seeded statuses are synthetic, assigned to give the dashboard a realistic
  spread. They are not an assessment of any organisation.
