"""Serve ComplianceTrack with waitress, a production WSGI server.

    python serve.py

`python app.py` starts Flask's development server, which Flask documents as
unsuitable for production. This entry point serves the same application with
waitress instead, after checking the configuration with
config.deployment_problems():

  APP_ENV=demo        (the default here) starts with warnings, for a
                      demonstration on one machine with the seeded accounts.
  APP_ENV=production  refuses to start while any check fails: published or
                      short secret, debug mode, no HTTPS cookie flag, an
                      account that still accepts the demonstration password,
                      or the demonstration account list on the sign-in page.

Settings, all optional: APP_HOST (default 127.0.0.1), APP_PORT (8080),
WAITRESS_THREADS (8), TRUSTED_PROXY (address of a reverse proxy that
terminates HTTPS and sets X-Forwarded-Proto). Binding to 127.0.0.1 keeps the
server reachable only through that proxy or from the machine itself.
"""
import os
import sys
import tempfile

from waitress import serve

from app import create_app
from config import deployment_problems
from src import db
from src.services import auth

DEMO_PASSWORD = "ChangeMe#2026"


def _evidence_writable(path):
    try:
        os.makedirs(path, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path):
            pass
        return True
    except OSError:
        return False


def main():
    app = create_app()
    mode = app.config["APP_ENV"] if app.config["APP_ENV"] == "production" else "demo"

    database_ok, demo_accounts = True, []
    with app.app_context():
        try:
            db.healthcheck()
            demo_accounts = auth.accounts_accepting(DEMO_PASSWORD)
        except Exception as exc:  # reported below as a configuration problem
            database_ok = False
            print(f"  database check failed: {exc}")

    problems = deployment_problems(app.config, mode, database_ok, demo_accounts,
                                   _evidence_writable(app.config["EVIDENCE_ROOT"]))
    print(f"\n  ComplianceTrack configuration check ({mode})")
    for level, message in problems:
        print(f"    {level.upper():<8}{message}")
    if not problems:
        print("    no problems found")
    if any(level == "error" for level, _ in problems):
        sys.exit("\n  Not started. Correct the errors above and run serve.py again.\n")

    host = os.environ.get("APP_HOST", "127.0.0.1")
    port = int(os.environ.get("APP_PORT", "8080"))
    threads = int(os.environ.get("WAITRESS_THREADS", "8"))
    proxy = {}
    if os.environ.get("TRUSTED_PROXY"):
        proxy = {"trusted_proxy": os.environ["TRUSTED_PROXY"],
                 "trusted_proxy_headers": {"x-forwarded-for", "x-forwarded-proto"},
                 "clear_untrusted_proxy_headers": True}

    print(f"\n  ComplianceTrack served by waitress at http://{host}:{port} "
          f"({threads} threads)\n")
    serve(app, host=host, port=port, threads=threads, ident="ComplianceTrack",
          **proxy)


if __name__ == "__main__":
    main()
