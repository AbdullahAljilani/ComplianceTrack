"""Authentication routes: sign in, sign out.

Kept separate from the auth service itself so the service stays callable from
every module without importing web routing.
"""
from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for

from src.services import audit, auth

bp = Blueprint("auth", __name__)


def _safe_next(target):
    """Only ever redirect to a path on this application, never to another host."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/"):
        return None
    return target


@bp.route("/login", methods=["GET", "POST"])
def login():
    if auth.current_user():
        return redirect(url_for(auth.landing_for(auth.current_user()["role"])))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = auth.verify_credentials(username, password)
        if user is None:
            # Recorded without a user id, since no user was authenticated.
            audit.record(audit.LOGIN_FAILURE, "user", 0,
                         {"username_attempted": username[:50]}, user_id=None)
            flash("Incorrect username or password.", "danger")
            return render_template("login.html", username=username), 401

        auth.login_user(user)
        audit.record(audit.LOGIN_SUCCESS, "user", user["user_id"],
                     {"role": user["role_name"]})
        return redirect(_safe_next(request.args.get("next"))
                        or url_for(auth.landing_for(user["role_name"])))

    return render_template("login.html", username="")


@bp.route("/logout", methods=["POST"])
def logout():
    user = auth.current_user()
    if user:
        audit.record(audit.LOGOUT, "user", user["user_id"])
    auth.logout_user()
    flash("You have been signed out.", "secondary")
    return redirect(url_for("auth.login"))
