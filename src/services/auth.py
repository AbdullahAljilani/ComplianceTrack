"""Shared Authentication and Authorization service.

This is the shared service drawn in the Unit 3 layered architecture. Every
module calls it rather than implementing its own checks, so authorisation is
enforced in one place on the server for every protected request. Hiding a link
in the interface is treated as presentation, never as an access control.
"""
import functools

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from flask import g, redirect, render_template, request, session, url_for

from src import db

# argon2-cffi's PasswordHasher uses Argon2id by default, as the Unit 3
# non-functional requirements specify.
_hasher = PasswordHasher()

# Capability matrix. Roles are data in the database; what each role may DO is
# policy and lives here so a single grant is visible in one place.
#
# Unit 5 extends the matrix with the four grants the Evidence Management and
# Remediation Tracker modules need. Two separations of duty are expressed here
# rather than in the modules:
#
#   - Nobody holds both 'evidence.upload' and 'evidence.review' as the only
#     route to an approval. The GRC Administrator holds both, so the service
#     layer additionally refuses a reviewer who is also the uploader, which is
#     the check that actually protects the Implemented gate.
#   - 'remediation.edit' lets the Internal Auditor raise a finding, but the
#     service layer limits moving an item and requesting its closure to the
#     item's owner or an administrator.
#
# Unit 6 adds 'remediation.verify' for FR-7. Closing an item now takes two
# people: the owner requests closure, and a holder of this grant who is
# neither the owner nor the requester verifies it. The service layer and a
# database constraint both refuse a self-verified closure.
PERMISSIONS = {
    "GRC Administrator": {"control.view", "control.edit",
                          "evidence.view", "evidence.upload", "evidence.review",
                          "remediation.view", "remediation.edit",
                          "remediation.verify",
                          "report.view", "audit.view"},
    "Control Owner": {"control.view", "control.edit",
                      "evidence.view", "evidence.upload",
                      "remediation.view", "remediation.edit", "report.view"},
    "Evidence Custodian": {"control.view", "evidence.view", "evidence.upload",
                           "remediation.view"},
    "Internal Auditor": {"control.view", "evidence.view", "evidence.review",
                         "remediation.view", "remediation.edit",
                         "remediation.verify", "report.view", "audit.view"},
    "Management": {"control.view", "evidence.view", "remediation.view",
                   "report.view"},
}


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_credentials(username: str, raw_password: str):
    """Return the user record on success, otherwise None.

    The same generic outcome is returned for an unknown username, a wrong
    password and a disabled account, so the response cannot be used to work out
    which usernames exist.
    """
    row = db.query_one(
        """
        SELECT u.user_id, u.username, u.full_name, u.password_hash,
               u.is_active, r.role_name
        FROM users u
        JOIN roles r ON r.role_id = u.role_id
        WHERE u.username = %s
        """,
        (username,),
    )
    if row is None:
        # Verify against a dummy hash anyway so the response time does not
        # reveal whether the username exists.
        try:
            _hasher.verify(_DUMMY_HASH, raw_password)
        except Exception:
            pass
        return None
    try:
        _hasher.verify(row["password_hash"], raw_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return None
    if not row["is_active"]:
        return None
    return row


_DUMMY_HASH = _hasher.hash("not-a-real-password")


def accounts_accepting(raw_password: str):
    """Usernames of active accounts that still accept this password.

    Used by serve.py before a deployment starts, to find accounts that still
    accept the published demonstration password. A default credential left in
    place is exactly the misconfiguration the deployment check exists to catch.
    """
    found = []
    for row in db.query("SELECT username, password_hash FROM users WHERE is_active"):
        try:
            _hasher.verify(row["password_hash"], raw_password)
            found.append(row["username"])
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            continue
    return found


def login_user(user):
    session.clear()
    session["user_id"] = user["user_id"]
    session["username"] = user["username"]
    session["full_name"] = user["full_name"]
    session["role"] = user["role_name"]
    session.permanent = False


def logout_user():
    session.clear()


def current_user():
    if "user_id" not in session:
        return None
    return {
        "user_id": session["user_id"],
        "username": session["username"],
        "full_name": session["full_name"],
        "role": session["role"],
    }


def has_permission(permission: str) -> bool:
    user = current_user()
    if user is None:
        return False
    return permission in PERMISSIONS.get(user["role"], set())


def may_change_control(user, owner_user_id) -> bool:
    """Object-level rule for changing one control's status (FR-1).

    'control.edit' says a role may edit controls in general. FR-1 narrows that
    to the controls assigned to the user, so a Control Owner may change only
    the controls they own, and a GRC Administrator may change any of them.
    The Unit 6 integration review found the route checked the role but not the
    owner, which let one owner change another owner's controls: the broken
    object-level access control OWASP ranks first.
    """
    if user is None:
        return False
    if user["role"] == "GRC Administrator":
        return True
    return (user["role"] == "Control Owner"
            and "control.edit" in PERMISSIONS.get(user["role"], set())
            and owner_user_id is not None
            and int(owner_user_id) == int(user["user_id"]))


def landing_for(role) -> str:
    """The page a role starts on after signing in.

    Unit 4 sent everyone to the dashboard, which the Evidence Custodian is not
    permitted to see, so a successful sign-in ended on an access-denied page.
    A role starts on the dashboard only if it may read reports.
    """
    if "report.view" in PERMISSIONS.get(role, set()):
        return "dashboard.index"
    return "controls.index"


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def requires(permission: str):
    """Server-side authorisation for a route. Applied to every protected view."""

    def decorator(view):
        @functools.wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not has_permission(permission):
                return render_template("403.html", needed=permission), 403
            return view(*args, **kwargs)

        return wrapped

    return decorator


def load_user_into_g():
    g.user = current_user()
