# ComplianceTrack

A centralized, web-based GRC compliance-tracking dashboard prototype aligned
with Saudi Arabia's National Cybersecurity Authority Essential Cybersecurity
Controls, ECC-2:2024. Built as the MSIT 5910 capstone project at the
University of the People.

ComplianceTrack is a compliance-tracking and workflow-management prototype.
**It does not certify an organization as compliant with ECC-2:2024.**
Compliance decisions, formal assessments, and audit conclusions remain the
responsibility of qualified personnel and the organization; this system
supports that judgment with a single, current, auditable view of control
status, evidence, and remediation activity.

## Project status

Design-stage (Unit 3 of 8). No application code has been implemented or
tested yet; Unit 4 begins implementation. See `docs/requirements.md` and
`design/` for the current design artifacts, all of which are proposed and
unimplemented unless stated otherwise.

## Modules

| Module | Purpose |
|---|---|
| Control Register | Track ECC-2:2024 control status, ownership, and review dates |
| Evidence Management | Versioned, hashed evidence uploads with reviewer approval |
| Remediation Tracker | Findings, owners, priorities, due dates, overdue detection |
| Reporting Dashboard | Role-dependent compliance summaries by domain |

## Scope

Governance domain (all 10 subdomains) plus five Cybersecurity Defense
subdomains: Asset Management, Identity and Access Management, Data and
Information Protection, Cryptography, and Web Application Security — 56 main
controls (91 clauses including sub-controls). The data model is designed to
be extensible to the remaining ECC-2:2024 domains without a schema redesign.
Out of scope: enterprise-platform integration, AI-driven recommendations,
automated telemetry collection, and any use of confidential organizational
data — synthetic data only throughout.

## Planned technology stack

Python (Flask) · PostgreSQL · HTML/CSS/Bootstrap · Git/GitHub · GitHub
Actions (from Unit 4) · PyTest (from Unit 5)

## Repository structure

```
src/            Application code, one folder per module (scaffolded; Unit 4+)
database/       Schema (PostgreSQL DDL) and future migration scripts
design/         Architecture and data-model diagrams (Graphviz source + PNG)
docs/           Requirements and other living project documentation
```

## Branching model

- `main` — reflects the state submitted for grading at each unit milestone.
- `develop` — integrates completed work ahead of the next milestone.
- `feature/*` — short-lived branches for one piece of work, merged into
  `develop` and deleted once complete.

Commit messages follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)
convention (`type(scope): description`).

## Author

Abdullah Aljilani — MSIT 5910, University of the People
