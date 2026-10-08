# Evaluation v0.3.1 (v0.3.1-testing-complete)

Run 2026-10-07T04:26:03+00:00 on Linux-6.18.44-fc-v77-x86_64-with-glibc2.39, Python 3.12.3, PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1), 2 logical CPUs, 8.4 GB. Server: waitress, 8 threads, 127.0.0.1.

| Measure | Result |
|---|---|
| Test suite | 124 of 124 passed in 5.2 s; coverage 83.8% |
| Accounts landing on a permitted page | 5 of 6 |
| Workflows completed as specified | 2 of 5 |
| Figures matching the SQL oracle | 22 of 22 |
| Slowest page, p95, one user | Dashboard: 19.2 ms |
| Dashboard at 20 users | 113.5 req/s, p95 212.0 ms, errors 0.0% |
| Server memory (RSS) | idle 38.2 MB, peak 111.0 MB |
| Simultaneous uploads (30) | 13 server errors, 12 digest mismatches, 0 orphan files |
| Tracker at 20000 items, p50 | 1680.4 ms (23526.3 KB) |

| Workflow | Result | Detail |
|---|---|---|
| W1 Evidence filed, independently approved, control recorded as Implemented | pass | 1-3-4: Partially Implemented -> Implemented; Implemented controls 8 -> 9 |
| W2 Finding raised, worked, closure verified by someone other than the owner | fail | item 17 Closed; closed by the owner, so no independent verification took place |
| W3 Compliance summary exported for an audit request | fail | no export function in this version (Unit 2 scope, Unit 3 Table 2) |
| W4 Implemented refused while no approved evidence exists | pass | 1-10-5 stayed Not Implemented; message: A control cannot be marked Implemented until supporting evidence has been approved by a reviewer. |
| W5 Owner refused a change to a control assigned to someone else | fail | 1-4-1 owned by ControlOwner02: Not Implemented -> Partially Implemented (changed) |
