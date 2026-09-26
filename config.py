"""Configuration loaded from the environment. No secret is ever hard-coded or
committed; .env is git-ignored and .env.example documents the required keys."""
import os

from dotenv import load_dotenv

load_dotenv()


class Config:
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
    # Set to True once the app is served over HTTPS, as the Unit 3 design requires.
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "").lower() == "true"
