# Deployment and configuration

How ComplianceTrack is built, configured and served. Written in Unit 6.
Sections marked *tested* were run against this repository at
`v0.4.0-integration` in the Linux environment the CI workflow mirrors; the
PowerShell forms follow the Windows sequence verified in Unit 5. Sections
marked *planned* describe the selected approach for an organisation adopting
the prototype and have not been exercised here.

ComplianceTrack tracks compliance information. It does not certify compliance
with NCA ECC-2:2024, and nothing in a deployment changes that.

## 1. Selected deployment approach

| Option | Considered for | Why not selected |
|---|---|---|
| Managed cloud platform (PaaS) | Least operations effort | Evidence about weak controls would leave the organisation's own infrastructure, which brings in the third-party and cloud requirements of ECC-2:2024 domain 4 and the hosting location questions they raise. |
| Containers (Docker Compose: app, PostgreSQL, evidence volume) | Identical environments everywhere | Recommended next step, not built: it adds a container runtime the solo build could not test, and the prototype has one instance. |
| **On-premise server, waitress behind an HTTPS reverse proxy** | **Selected** | Keeps evidence and the database inside the organisation, needs nothing beyond Python and PostgreSQL, and runs the same on Windows Server and Linux. |

Release strategy: an in-place release of a tagged version from `main`, with a
database backup taken first and the previous tag kept for rollback. Blue-green
and canary releases need two running environments and live traffic to compare,
which a single internal instance does not have.

There is no continuous deployment, by the decision recorded in Unit 4: a
release is a reviewed, manual step, consistent with the reviewer-approval
principle the application itself enforces.

## 2. System prerequisites

| Component | Version | Notes |
|---|---|---|
| Operating system | Windows 11 or Windows Server 2022; Ubuntu 24.04 LTS | Developed on Windows 11; CI runs on Ubuntu. |
| Python | 3.12 on Windows (3.11 or later on Linux) | `psycopg2-binary==2.9.9` publishes Windows wheels up to Python 3.12 only. |
| PostgreSQL | 16 or later | Tested on 16. |
| Git | any recent | Clone and check out a release tag. |
| Python packages | `requirements.txt` (runtime), `requirements-dev.txt` (tests and tools) | All pinned. |

## 3. Environment variables

Read once, in `config.py`. Copy `.env.example` to `.env`; `.env` is git-ignored.

| Variable | Purpose | Default | Production value |
|---|---|---|---|
| `FLASK_SECRET_KEY` | Signs the session cookie | development fallback | 64 random hex characters. `serve.py` refuses a placeholder or anything under 32 characters. |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | PostgreSQL connection | localhost, 5432, compliancetrack, postgres, empty | A dedicated database account, not `postgres`. |
| `EVIDENCE_ROOT` | Folder for evidence files, outside the web root | `evidence_store` in the project | A protected, backed-up volume. |
| `APP_ENV` | `development`, `demo` or `production` | development | `production` |
| `FLASK_DEBUG` | Debug mode for `python app.py` | off | Never set. |
| `SESSION_COOKIE_SECURE` | Cookie sent over HTTPS only | false | true |
| `SHOW_DEMO_ACCOUNTS` | Lists the seeded accounts on the sign-in page | true | false |
| `APP_HOST`, `APP_PORT` | Where `serve.py` listens | 127.0.0.1, 8080 | 127.0.0.1, behind the proxy |
| `WAITRESS_THREADS` | Worker threads | 8 | 8 |
| `TRUSTED_PROXY` | Reverse proxy allowed to set `X-Forwarded-Proto` | unset | The proxy's address |

## 4. Install and set up (tested)

Windows PowerShell, from the project folder. `$psql` finds psql without editing
PATH, whichever PostgreSQL version is installed.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env        # then set FLASK_SECRET_KEY and DB_PASSWORD

$psql = (Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\psql.exe" |
         Sort-Object FullName -Descending | Select-Object -First 1).FullName
$env:PGPASSWORD = "your-postgres-password"     # this window only, never saved
& $psql -U postgres -c "CREATE DATABASE compliancetrack;"
Get-Content database\load_order.txt | Where-Object { $_ -and -not $_.StartsWith("#") } |
  ForEach-Object { & $psql -U postgres -d compliancetrack -v ON_ERROR_STOP=1 -f "database\$_" }
```

Linux:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
createdb -U postgres compliancetrack
grep -v '^#' database/load_order.txt | sed '/^$/d' | while read -r f; do
  psql -U postgres -d compliancetrack -v ON_ERROR_STOP=1 -f "database/$f"; done
```

`database/load_order.txt` is the single list of SQL files in build order. The CI
workflow and `scripts/evaluate_system.py` read the same file.

## 5. Build steps (tested)

```powershell
# Demonstration data only. A real deployment loads its own controls and users.
.\.venv\Scripts\python.exe scripts\seed_evidence_demo.py
.\.venv\Scripts\python.exe scripts\reconcile_evidence_gate.py

# Verify before serving.
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt
```

## 6. Run

| Purpose | Command | Server |
|---|---|---|
| Development | `.\.venv\Scripts\python.exe app.py` | Flask development server, http://127.0.0.1:5000 |
| Demonstration | `$env:APP_ENV="demo"; .\.venv\Scripts\python.exe serve.py` | waitress, http://127.0.0.1:8080, warnings printed |
| Production | `APP_ENV=production`, then `serve.py` | waitress; refuses to start while any check fails |

`serve.py` checks the configuration before it starts (tested): a published or
short secret, debug mode, an unreachable database or evidence folder stop it
in every mode; the HTTPS cookie flag, accounts that still accept the
demonstration password, and the sign-in account list are warnings in `demo`
and errors in `production`.

Planned, not exercised here:

- **Reverse proxy.** IIS with URL Rewrite and Application Request Routing on
  Windows Server, or nginx on Linux, terminates TLS, sets
  `Strict-Transport-Security` and `X-Forwarded-Proto`, and forwards to
  `127.0.0.1:8080`. Set `TRUSTED_PROXY` to the proxy's address and
  `SESSION_COOKIE_SECURE=true`. Do not enable response caching for the
  application; every page already sends `Cache-Control: no-store`.
- **Service.** Run `serve.py` as a service so it restarts with the machine:
  a systemd unit on Linux, or a service wrapper on Windows Server.
- **Backups.** `pg_dump` of the database and a copy of `EVIDENCE_ROOT`, taken
  together, because each evidence record names a file and its SHA-256 digest.

## 7. Release and rollback (planned)

1. Back up the database (`pg_dump -Fc`) and the evidence folder.
2. Check out the release tag, for example `git checkout v0.4.0-integration`.
3. Install `requirements.txt`; apply any migration added since the running
   release, in the order `load_order.txt` gives.
4. Run `serve.py` once with `APP_ENV=production` and read the configuration
   check; correct any error before going further.
5. Restart the service and sign in with a test account.

Rollback is the reverse: restore the backup and check out the previous tag.
A migration is only rolled back by restoring the backup, which is why the
backup is step 1.

## 8. What configuration management covers

Versioned in Git: application code, templates, SQL schema and migrations,
`load_order.txt`, pinned dependency lists, the lint rule set (`ruff.toml`) and
the CI workflow, each release tagged. Not versioned, and therefore backed up
instead: `.env` secrets, the database contents and the evidence files.
