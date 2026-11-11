"""Password policy, hashing, CSRF, session handling and route guards."""
import hmac
import re
import secrets
import time
from functools import wraps

from flask import abort, flash, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import preferences, users
from .config import Config
from .rbac import can, role_allowed_for_portal

HASH_PREFIXES = ("pbkdf2:", "scrypt:")
EMAIL_RE = re.compile(r"^[a-z][a-z'-]*(?:\.[a-z0-9][a-z0-9'-]*)+@carelon\.com$")

STAGE_SETUP_PASSWORD = "setup_password"
STAGE_SETUP_EMAIL = "setup_email"
STAGE_ACTIVE = "active"


# ---------------- passwords ----------------
def is_hashed(stored):
    return isinstance(stored, str) and stored.startswith(HASH_PREFIXES)


def hash_password(password):
    return generate_password_hash(password, method="pbkdf2:sha256:600000")


def verify_hash(stored, password):
    return is_hashed(stored) and check_password_hash(stored, password)


def matches_temporary(stored, password):
    return stored is not None and hmac.compare_digest(str(stored).encode(), password.encode())


def password_errors(password):
    errors = []
    if len(password) < 8:
        errors.append("at least 8 characters")
    if not re.search(r"[A-Z]", password):
        errors.append("1 uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("1 lowercase letter")
    if not re.search(r"\d", password):
        errors.append("1 number")
    return errors


def is_carelon_email(email):
    return bool(EMAIL_RE.fullmatch(email.strip().lower())) and ".." not in email


# ---------------- CSRF ----------------
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def verify_csrf():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token") or ""
        expected = session.get("_csrf") or ""
        if not expected or not hmac.compare_digest(sent, expected):
            abort(400, "Your session expired. Please refresh the page and try again.")


# ---------------- session ----------------
def start_session(row, portal, stage):
    session.clear()
    session.permanent = True
    now = int(time.time())
    session["auth"] = {"domain": users.domain_of(row), "portal": portal, "stage": stage, "iat": now, "seen": now}
    csrf_token()


def current_auth():
    auth = session.get("auth")
    if not auth:
        return None
    now = int(time.time())
    if now - auth.get("seen", 0) > Config.SESSION_IDLE.total_seconds() or now - auth.get(
        "iat", 0
    ) > Config.PERMANENT_SESSION_LIFETIME.total_seconds():
        session.clear()
        flash("Your session has expired. Please sign in again.", "info")
        return None
    auth["seen"] = now
    session["auth"] = auth
    return auth


def set_stage(stage):
    auth = session["auth"]
    auth["stage"] = stage
    session["auth"] = auth


def end_session():
    session.clear()


def _load_user(auth):
    """Re-validate the user and their role against the database on every protected request."""
    row = users.get_by_domain(auth["domain"])
    if not row or not role_allowed_for_portal(users.role_of(row), auth["portal"]):
        session.clear()
        flash("Your access has changed. Please sign in again.", "error")
        return None
    g.user_row = row
    g.role = users.role_of(row)
    g.portal = auth["portal"]
    g.profile = users.profile(row)
    g.profile_map = dict(g.profile)
    if auth["stage"] == STAGE_ACTIVE and "prefs" not in session:
        session["prefs"] = preferences.load(users.domain_of(row))
    return row


def login_required(permission=None, program=None):
    """Protect a page: requires a completed account, a valid role for the portal, the permission and
    (optionally) that the user has entered the given program module."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            auth = current_auth()
            if not auth:
                return redirect(url_for("auth.login", next=request.path))
            if auth["stage"] == STAGE_SETUP_PASSWORD:
                return redirect(url_for("auth.setup_password"))
            if auth["stage"] == STAGE_SETUP_EMAIL:
                return redirect(url_for("auth.setup_email"))
            if not _load_user(auth):
                return redirect(url_for("auth.login"))
            if permission and not can(g.role, permission):
                abort(403)
            if program and session.get("program") != program:
                return redirect(url_for("main.programs"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


def setup_required(stage):
    """Guard for first-time account setup steps."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            auth = current_auth()
            if not auth:
                return redirect(url_for("auth.login"))
            if auth["stage"] == STAGE_ACTIVE:
                return redirect(url_for("main.programs"))
            if auth["stage"] != stage:
                endpoint = "auth.setup_password" if auth["stage"] == STAGE_SETUP_PASSWORD else "auth.setup_email"
                return redirect(url_for(endpoint))
            if not _load_user(auth):
                return redirect(url_for("auth.login"))
            return view(*args, **kwargs)

        return wrapped

    return decorator
