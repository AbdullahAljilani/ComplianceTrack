"""Shared Audit Logging service.

The second shared service in the Unit 3 architecture. Modules call record()
instead of writing their own log rows, so the trail is consistent across the
application and every entry is written inside the same transaction as the change
it describes. If the change rolls back, so does its log row.
"""
import json

from src import db
from src.services import auth

LOGIN_SUCCESS = "LOGIN_SUCCESS"
LOGIN_FAILURE = "LOGIN_FAILURE"
LOGOUT = "LOGOUT"
STATUS_CHANGE = "STATUS_CHANGE"


def record(action, entity_type, entity_id, details=None, user_id=None):
    if user_id is None:
        user = auth.current_user()
        user_id = user["user_id"] if user else None
    db.execute(
        """
        INSERT INTO audit_log (user_id, action, entity_type, entity_id, details)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (user_id, action, entity_type, entity_id,
         json.dumps(details) if details is not None else None),
    )


def recent(limit=50):
    limit = max(1, min(int(limit), 200))
    return db.query(
        """
        SELECT a.audit_id, a.action, a.entity_type, a.entity_id,
               a.occurred_at, a.details, u.username
        FROM audit_log a
        LEFT JOIN users u ON u.user_id = a.user_id
        ORDER BY a.occurred_at DESC, a.audit_id DESC
        LIMIT %s
        """,
        (limit,),
    )
