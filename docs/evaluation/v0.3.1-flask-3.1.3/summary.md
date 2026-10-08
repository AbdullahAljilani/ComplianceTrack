# Evaluation v031-flask313 (v0.3.1-testing-complete)

Run 2026-10-07T04:43:53+00:00 on Linux-6.18.44-fc-v77-x86_64-with-glibc2.39, Python 3.12.3, PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1), 2 logical CPUs, 8.4 GB. Server: waitress, 8 threads, 127.0.0.1.

| Measure | Result |
|---|---|
| Slowest page, p95, one user | Dashboard: 21.6 ms |
| Dashboard at 20 users | 115.3 req/s, p95 216.5 ms, errors 0.0% |
| Server memory (RSS) | idle 37.5 MB, peak 110.6 MB |
