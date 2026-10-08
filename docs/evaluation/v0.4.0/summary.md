# Evaluation v0.4.0 (6211d57)

Run 2026-10-07T04:33:31+00:00 on Linux-6.18.44-fc-v77-x86_64-with-glibc2.39, Python 3.12.3, PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1), 2 logical CPUs, 8.4 GB. Server: waitress, 8 threads, 127.0.0.1.

| Measure | Result |
|---|---|
| Test suite | 223 of 223 passed in 11.44 s; coverage 88.3% |
| Accounts landing on a permitted page | 6 of 6 |
| Workflows completed as specified | 5 of 5 |
| Figures matching the SQL oracle | 27 of 27 |
| Slowest page, p95, one user | Dashboard: 22.0 ms |
| Dashboard at 20 users | 101.5 req/s, p95 243.5 ms, errors 0.0% |
| Server memory (RSS) | idle 38.3 MB, peak 112.3 MB |
| Simultaneous uploads (30) | 0 server errors, 0 digest mismatches, 0 orphan files |
| Tracker at 20000 items, p50 | 399.7 ms (33.2 KB) |

| Workflow | Result | Detail |
|---|---|---|
| W1 Evidence filed, independently approved, control recorded as Implemented | pass | 1-3-4: Partially Implemented -> Implemented; Implemented controls 8 -> 9 |
| W2 Finding raised, worked, closure verified by someone other than the owner | pass | item 20: Open -> In Progress -> Pending Verification -> Closed |
| W3 Compliance summary exported for an audit request | pass | domain summary 9 lines; control extract 68 rows for 68 tracked controls; boundary statement present: True |
| W4 Implemented refused while no approved evidence exists | pass | 1-10-5 stayed Not Implemented; message: A control cannot be marked Implemented until supporting evidence has been approved by a reviewer. |
| W5 Owner refused a change to a control assigned to someone else | pass | 1-4-1 owned by ControlOwner02: Not Implemented -> Not Implemented (refused) |
