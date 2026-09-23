# ComplianceTrack

A centralized, web-based GRC compliance-tracking dashboard prototype aligned with Saudi Arabia's National Cybersecurity Authority Essential Cybersecurity Controls, ECC-2:2024. This project is being developed as the MSIT 5910 capstone project at the University of the People.

ComplianceTrack is a compliance-tracking and workflow-management prototype. **It does not certify an organization as compliant with ECC-2:2024.** Compliance decisions, formal assessments, and audit conclusions remain the responsibility of qualified personnel and the organization. The system provides a centralized view of control status, evidence, and remediation activities to support this work.

## Project Status

Design stage, Unit 3 of 8. Application code has not been implemented or tested yet. Implementation begins in Unit 4.

The current design materials are available in the `docs/requirements.md` and `design/` directories. These materials represent the proposed design unless otherwise stated.

## Modules

| Module              | Purpose                                                                 |
| ------------------- | ----------------------------------------------------------------------- |
| Control Register    | Track ECC-2:2024 control status, ownership, and review dates            |
| Evidence Management | Manage evidence uploads with versioning, hashing, and reviewer approval |
| Remediation Tracker | Track findings, owners, priorities, due dates, and overdue items        |
| Reporting Dashboard | Provide compliance summaries based on user roles                        |

## Scope

The project covers the Governance domain, including all 10 subdomains, and five Cybersecurity Defense subdomains:

* Asset Management
* Identity and Access Management
* Data and Information Protection
* Cryptography
* Web Application Security

The current scope includes 56 main controls and 91 clauses, including sub-controls. The data model is designed so that the remaining ECC-2:2024 domains can be added later without redesigning the database schema.

The following items are outside the current project scope:

* Enterprise platform integration
* AI-driven recommendations
* Automated telemetry collection
* Use of confidential organizational data

Synthetic data will be used throughout the project.

## Planned Technology Stack

* Python with Flask
* PostgreSQL
* HTML, CSS, and Bootstrap
* Git and GitHub
* GitHub Actions, starting from Unit 4
* PyTest, starting from Unit 5

## Repository Structure

```text
src/            Application code, with one folder for each module
                (scaffolded for Unit 4 and later)

database/       PostgreSQL database schema and future migration scripts

design/         Architecture and data-model diagrams
                (Graphviz source files and PNG images)

docs/           Requirements and other project documentation
```

## Branching Model

* `main` reflects the state submitted for grading at each unit milestone.
* `develop` integrates completed work ahead of the next milestone.
* `feature/*` branches are short-lived branches for one piece of work. They are merged into `develop` and deleted once the work is complete.

Commit messages follow the Conventional Commits format:

`type(scope): description`

## Author

Abdullah Aljilani
MSIT 5910, University of the People
