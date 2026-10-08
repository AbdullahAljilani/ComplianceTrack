# Branching, tagging and release model

ComplianceTrack is built by one student across one semester. The model below
is a reduced Git Flow: it keeps the separation between stable and in-progress
work that makes tags meaningful, and drops the parts of Git Flow that only earn
their cost on a team with parallel releases to support.

## Branches

| Branch | Purpose |
|---|---|
| `main` | Stable. Only ever updated by a merge from `develop`, and every commit on it carries a tag. A marker or an examiner cloning this branch gets a state that runs. |
| `develop` | Integration. Feature branches merge here first, so a half-finished module never sits on `main`. |
| `feature/<unit>-<module>` | One unit of work, named for the unit that produced it and the module it changes. Short-lived: created from `develop`, merged back, then deleted. |
| `fix/<unit>-<defect>` | A correction to work already merged, named for the defect. Same lifecycle as a feature branch. Used in Units 5 and 6 for defects found by tests and evaluation. |

Feature branches are merged with `--no-ff`, so each merge commit records the
unit of work as a group rather than scattering its commits into a flat line.
On a solo project this is the main reason to branch at all: the history stays
readable months later, when the final report has to explain what was built
when.

## Tags

Tags are annotated, not lightweight, so each one carries a message, an author
and a date that `git show` will display. They mark course milestones rather
than arbitrary points.

| Tag | Milestone |
|---|---|
| `v0.1.0-design` | Unit 3. Schema, architecture and interface design; no application code yet. |
| `v0.2.0-prototype` | Unit 4. First running prototype: authentication, Control Register, Reporting Dashboard. |
| `v0.3.0-core-logic` | Unit 5. Evidence Management, Remediation Tracker and the compliance scoring service implemented. |
| `v0.3.1-testing-complete` | Unit 5. Unit and integration test suites complete, and the two defects they found fixed. |
| `v0.4.0-integration` | Unit 6. Integration review fixes, feature completion against the Unit 3 design, deployment configuration and the system evaluation. |

The numbering stays below `1.0.0` deliberately. This is a prototype, and a
`1.0.0` would claim a stability it does not have.

## Releases

Each tag on `main` is published as a GitHub release. The release notes state
what changed, what is implemented, and what is still only designed, so the
state being claimed at that point is written down rather than inferred from
the code. Keeping that record is what makes the tag useful for monitoring
progress: the difference between two releases is a plain statement of a
semester's worth of work, not a diff someone has to read.

## Why this helps a solo project

Tagging at each unit means an earlier state can be recovered exactly. When the
Unit 5 test suite found that an oversized upload returned a bare framework
error page, the fix could be written and compared against `v0.3.0-core-logic`
without disturbing anything else. Without the tag, the comparison point would
have been a commit hash nobody remembers.
