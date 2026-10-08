"""Configuration loaded from the environment. No secret is ever hard-coded or
committed; .env is git-ignored and .env.example documents the required keys.

Unit 6 adds the deployment checks. Every setting that decides whether the
application is safe to serve is read here, in one place, and
deployment_problems() states the rules serve.py applies before it will start.
"""
import os

from dotenv import load_dotenv

load_dotenv()

# Values that must never protect a served instance: the development fallback
# below and the placeholder printed in .env.example. Both are public in the
# repository, so anyone could sign a session cookie with them.
KNOWN_PLACEHOLDER_SECRETS = {"dev-only-insecure-key",
                             "change-this-to-a-long-random-value"}
MIN_SECRET_LENGTH = 32


def _flag(name, default="false"):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


class Config:
    # development: python app.py on the developer's own machine.
    # demo:        python serve.py for a demonstration; risky settings warn.
    # production:  python serve.py behind HTTPS; risky settings refuse to start.
    APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()
    DEBUG = _flag("FLASK_DEBUG")
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-only-insecure-key")
    DB = {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": os.environ.get("DB_PORT", "5432"),
        "dbname": os.environ.get("DB_NAME", "compliancetrack"),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", ""),
    }
    # Evidence is written outside the web root and is never served by Flask as
    # a static path, so an uploaded file cannot be requested back over HTTP.
    EVIDENCE_ROOT = os.environ.get(
        "EVIDENCE_ROOT",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "evidence_store"),
    )
    MAX_CONTENT_LENGTH = 12 * 1024 * 1024      # hard cap before the view runs
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # The sign-in page lists the synthetic demonstration accounts only while
    # this is true. A deployment that holds real accounts switches it off.
    SHOW_DEMO_ACCOUNTS = _flag("SHOW_DEMO_ACCOUNTS", "true")
    # Set to True once the app is served over HTTPS, as the Unit 3 design requires.
    SESSION_COOKIE_SECURE = _flag("SESSION_COOKIE_SECURE")


def deployment_problems(settings, mode, database_ok, demo_password_accounts,
                        evidence_writable):
    """Judge whether the application may be served in this mode.

    Returns a list of (level, message) pairs, level being 'error' or 'warning'.
    A pure function: everything it judges is passed in, so the rules can be
    tested without a server, a database or an environment.

    Errors stop serve.py in every mode. Three settings are acceptable for a
    demonstration on one machine but not for a deployment holding real
    accounts; they are warnings in 'demo' and errors in 'production'.
    """
    strict = mode == "production"
    found = []

    secret = settings.get("SECRET_KEY") or ""
    if secret in KNOWN_PLACEHOLDER_SECRETS or len(secret) < MIN_SECRET_LENGTH:
        found.append(("error", "FLASK_SECRET_KEY is missing, a published placeholder, "
                               f"or shorter than {MIN_SECRET_LENGTH} characters."))
    if settings.get("DEBUG"):
        found.append(("error", "FLASK_DEBUG is on. Debug mode must never be reachable "
                               "from a network."))
    if not database_ok:
        found.append(("error", "The database cannot be reached with the DB_* settings."))
    if not evidence_writable:
        found.append(("error", "EVIDENCE_ROOT does not exist or is not writable."))

    def by_mode(message):
        found.append(("error" if strict else "warning", message))

    if not settings.get("SESSION_COOKIE_SECURE"):
        by_mode("SESSION_COOKIE_SECURE is off. Serve the application over HTTPS "
                "and set it to true.")
    if demo_password_accounts:
        by_mode(f"{len(demo_password_accounts)} active account(s) still accept the "
                f"published demonstration password.")
    if settings.get("SHOW_DEMO_ACCOUNTS"):
        by_mode("SHOW_DEMO_ACCOUNTS is on, so the sign-in page lists account names.")
    return found
