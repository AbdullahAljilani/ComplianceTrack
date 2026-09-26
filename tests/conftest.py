"""Shared test fixtures.

The unit tests in this directory deliberately do not touch PostgreSQL. A unit
test is meant to exercise one component in isolation, and a test that needs a
running database is testing the database as much as the code
(Amazon Web Services, n.d.). Where a function under test would normally read
rows, a stub stands in for the data layer and returns a fixed result, so the
test asserts on the logic and nothing else.

The integration checks that do need a live database are kept in
test_integration_db.py and are marked so they can be selected or skipped
separately.
"""
from datetime import date

import pytest


class StubDb:
    """Minimal stand-in for src.db.

    Records the SQL it is given and replays queued results. Recording the SQL
    lets a test assert that values were passed as bound parameters rather than
    formatted into the statement, which is the property the Unit 3 design
    relies on to prevent injection.
    """

    def __init__(self, results=None):
        self._results = list(results or [])
        self.calls = []

    def _next(self):
        return self._results.pop(0) if self._results else []

    def query(self, sql, params=None):
        self.calls.append((sql, params))
        return self._next()

    def query_one(self, sql, params=None):
        self.calls.append((sql, params))
        result = self._next()
        return result[0] if isinstance(result, list) and result else result or None

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return 1


@pytest.fixture
def stub_db():
    return StubDb()


@pytest.fixture
def today():
    """A fixed reference date.

    Every function that reasons about time takes the date as an argument
    instead of calling date.today(), so these tests give the same result on any
    day they are run. A test that silently changes behaviour overnight is worse
    than no test.
    """
    return date(2026, 9, 26)


def remediation(status="Open", priority="Medium", due=date(2026, 10, 1)):
    """Build one remediation item in the shape the service layer receives."""
    return {"status": status, "priority": priority, "due_date": due}
