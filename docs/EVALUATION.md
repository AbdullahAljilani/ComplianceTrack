# Unit 6 system evaluation

How the integrated prototype was evaluated, and what the evaluation found.
Every number below comes from `scripts/evaluate_system.py`; the raw results
are in `docs/evaluation/v0.3.1/` (before the Unit 6 changes) and
`docs/evaluation/v0.4.0/` (after them). Nothing here assesses any
organisation's compliance; the figures describe the software.

## Method

Both versions were measured the same way, on the same host, one after the
other: a clean Ubuntu 24.04 environment with 2 logical CPUs and 8 GB of memory,
Python 3.12, PostgreSQL 16 and waitress 3.0.2 with 8 threads. Each run builds
its own database from the repository's SQL files and seeds it with the same
synthetic data, so the two versions are compared on identical data. Response
times are measured from a client on the same host, so they exclude network
distance and browser rendering; they are server response times.

| Measure | How it is taken | Target |
|---|---|---|
| Test suite | pytest under coverage.py, statement and branch | all pass |
| Role landing | each of the six seeded accounts signs in and follows the redirect | 6 of 6 reach a permitted page |
| Workflows | five end-to-end workflows driven over HTTP (below) | 5 of 5 behave as specified |
| Accuracy | every dashboard figure, every tracker state, the JSON summary and the CSV extract compared with an independent SQL oracle | 100% agreement |
| Latency | 20 warm-up and 200 timed requests per page, one user; p50, p95, max | p95 under 100 ms (felt as instantaneous) |
| Throughput | dashboard at 1, 5, 10 and 20 concurrent users, 400 requests per level, three runs, median reported | 0% errors; p95 under 1 s at 20 users |
| Memory | resident memory of the server process, idle and sampled every 50 ms under load | recorded |
| Integrity | 15 pairs of simultaneous uploads to one control | 0 server errors, 0 digest mismatches, 0 orphan files |
| Scale | dashboard and tracker response as remediation items grow to 20,000 | under 1 s |

The latency targets follow Nielsen's response-time limits: about 0.1 s feels
instantaneous and about 1 s keeps the user's flow of thought uninterrupted.
The prototype has no stated service level, so these limits stand in for one.

Workflows (the Unit 2 SMART goal asked for at least three realistic workflows
covering the evidence and remediation modules):

| Id | Workflow | Roles | Interactions |
|---|---|---|---|
| W1 | Evidence filed, independently approved, control recorded as Implemented | Custodian, Auditor, Owner | 6 |
| W2 | Finding raised, worked, closure verified by someone other than the owner | Auditor, Owner | 7 |
| W3 | Compliance summary exported for an audit request | Management | 3 |
| W4 | Implemented refused while no approved evidence exists | Owner | 2 |
| W5 | Owner refused a change to a control assigned to someone else | Owner | 2 |

## Results

| Measure | v0.3.1 | v0.4.0 |
|---|---|---|
| Tests passed | 124 of 124 | 223 of 223 |
| Coverage (statements and branches) | 83.8% | 88.3% |
| Accounts reaching a permitted page | 5 of 6 | 6 of 6 |
| Workflows behaving as specified | 2 of 5 | 5 of 5 |
| Figures matching the oracle | 22 of 22 | 27 of 27 |
| Slowest page p95, one user | 19.2 ms | 22.0 ms |
| Dashboard throughput, 10 users (median) | 117.2 req/s | 102.7 req/s |
| Dashboard p95, 20 users (median) | 212.0 ms | 243.5 ms |
| Errors under load | 0% | 0% |
| Server memory, idle / peak | 38.2 / 111.0 MB | 38.3 / 112.3 MB |
| Simultaneous uploads (30) | 13 server errors, 12 digest mismatches | 0, 0, 0 orphan files |
| Tracker at 20,000 items, p50 | 1,680 ms, 23.5 MB page | 400 ms, 33 KB page |
| Dashboard at 20,000 items, p50 | 94 ms | 117 ms |

Reading the results:

- **Correctness held throughout.** Every figure the dashboard, tracker, API and
  export show agreed with the oracle in both versions.
- **The workflows found the functional gaps.** At v0.3.1, W2 failed because
  the owner closed their own item (FR-7), W3 because there was no export, and
  W5 because one owner could change another's control (FR-1). All three pass
  at v0.4.0.
- **The concurrency test found the integrity defect.** 12 of 15 simultaneous
  upload pairs left a record whose SHA-256 digest no longer matched its file.
  None did after the fix.
- **Speed stayed far inside the targets, at a small cost.** Single-user p95
  rose by about 3 ms and dashboard throughput fell by about 10 to 12 per cent,
  because each dashboard request now does more: the per-domain breakdown FR-8
  asks for (about 0.6 ms of database work measured in-process) and a larger
  page. The Flask upgrade is not the cause: v0.3.1 run with Flask 3.1.3 gave
  115.0 req/s at 10 users, within the spread of its Flask 3.0.3 runs
  (`docs/evaluation/v0.3.1-flask-3.1.3/`). Paging cut the tracker's response
  at 20,000 items by about three quarters and its page from 23.5 MB to 33 KB.

## Heuristic review (qualitative)

The interface was reviewed against Nielsen's ten usability heuristics on both
versions, rating each problem on Nielsen's 0 to 4 severity scale (1 cosmetic,
2 minor, 3 major). It is an expert review, not a test with users.

| # | Finding at v0.3.1 | Heuristic | Severity | v0.4.0 |
|---|---|---|---|---|
| 1 | Sign-in page lists accounts that no longer exist, so its hint cannot be used to sign in | 10 Help and documentation | 3 | Fixed |
| 2 | Evidence Custodian lands on "Access denied" after signing in; its only button leads to another refusal | 3 User control and freedom | 3 | Fixed |
| 3 | An owner closes their own remediation item from a one-line box in each row, with no second check | 5 Error prevention | 3 | Fixed |
| 4 | A Control Owner is offered, and allowed, a status change on another owner's control | 5 Error prevention | 3 | Fixed |
| 5 | Tracker tiles mix whole-register counts with a filtered overdue count | 4 Consistency and standards | 2 | Fixed |
| 6 | No export; figures for an audit request must be retyped | 7 Flexibility and efficiency | 2 | Fixed |
| 7 | The tracker shows every item on one page | 7 Flexibility and efficiency | 2 | Fixed |
| 8 | "Start" offered on items already in progress; two forms per row | 8 Aesthetic and minimalist design | 1 | Fixed |
| 9 | Buttons styled inconsistently; digest column named only macOS fonts | 4 Consistency and standards | 1 | Fixed |
| 10 | No help page beyond the inline notes | 10 Help and documentation | 1 | Open |
| 11 | A status change has no confirmation step (it is logged and reversible) | 3 User control and freedom | 1 | Open |

Strengths the review recorded: error messages name the rule that was applied
(the evidence gate, file format and size, a rejection without a reason); every
action reports its outcome; the vocabulary is the ECC's own; and the
no-certification boundary appears on every page and in every export.

## Reproducing

```
pip install -r requirements-dev.txt
python scripts/evaluate_system.py --label my-run
```

The script reads the DB_* settings from `.env`, builds `compliancetrack_eval`
and `compliancetrack_scale`, and writes `results.json`, `latency.csv` and
`summary.md` to `docs/evaluation/my-run/`. Absolute times depend on the
machine; comparisons should be made between runs on the same machine.

## Limits of this evaluation

Server response times on one host, not end-to-end times in a browser over a
network; synthetic data; 20 simulated users rather than real ones; and a
heuristic review by the developer rather than usability testing with GRC
staff, which remains the most important evaluation still to do.
