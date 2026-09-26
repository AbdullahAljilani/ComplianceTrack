"""Data layer access.

Every query in this module and its callers passes user-supplied values as bound
parameters. No SQL string anywhere in ComplianceTrack is built by concatenating
or formatting a user-supplied value, which is the defence against the injection
category OWASP continues to rank among the most critical web application risks
and which the Unit 3 design commits the implementation to.
"""
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from flask import current_app, g


def _connect():
    return psycopg2.connect(**current_app.config["DB_SETTINGS"])


def get_conn():
    """One connection per request, closed by close_conn on teardown."""
    if "db_conn" not in g:
        g.db_conn = _connect()
    return g.db_conn


def close_conn(exc=None):
    conn = g.pop("db_conn", None)
    if conn is None:
        return
    # An unhandled exception must not leave a half-applied transaction behind.
    if exc is None:
        conn.commit()
    else:
        conn.rollback()
    conn.close()


@contextmanager
def cursor():
    cur = get_conn().cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield cur
    finally:
        cur.close()


def query(sql, params=None):
    with cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def query_one(sql, params=None):
    with cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchone()


def execute(sql, params=None):
    """Run a write and return the affected row count."""
    with cursor() as cur:
        cur.execute(sql, params or ())
        return cur.rowcount


def healthcheck():
    """Used by the startup banner so a misconfigured database fails loudly."""
    row = query_one("SELECT current_database() AS db, version() AS v;")
    return row["db"], row["v"].split(",")[0]
