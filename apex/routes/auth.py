"""Login, first-time account setup and logout."""
import logging

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from .. import users
from ..config import Config
from ..rbac import PORTAL_ADMIN, PORTAL_ASSOCIATE, role_allowed_for_portal
from ..security import (
    STAGE_ACTIVE,
    STAGE_SETUP_EMAIL,
    STAGE_SETUP_PASSWORD,
    current_auth,
    end_session,
    hash_password,
    is_carelon_email,
    is_hashed,
    matches_temporary,
    password_errors,
    set_stage,
    setup_required,
    start_session,
    verify_hash,
)
from ..supabase import SupabaseError, supabase

bp = Blueprint("auth", __name__)
log = logging.getLogger(__name__)

INVALID_CREDENTIALS = "Invalid username or password."
UNAUTHORIZED = {
    PORTAL_ASSOCIATE: "You are not authorized to use Associate Login.",
    PORTAL_ADMIN: "You are not authorized to use Admin Login.",
}
SERVICE_DOWN = "APEX could not reach the database. Please try again shortly."


def _safe_next(target):
    return target if target and target.startswith("/") and not target.startswith("//") else None


def _authenticate(row, password):
    """Return the next stage for valid credentials, or None when they are invalid."""
    domain = users.domain_of(row)
    stored = users.password_of(row)
    if not is_hashed(stored):
        return STAGE_SETUP_PASSWORD if matches_temporary(stored, password) else None

    if supabase.sign_in(users.auth_email(domain), password) is None:
        if not verify_hash(stored, password):
            return None
        # Table hash is valid but the Auth identity is missing/out of sync: re-provision it.
        supabase.admin_upsert_user(users.auth_user_id(domain), users.auth_email(domain), password,
                                   {"domain": domain, "carelon_email": users.email_of(row)})
    return STAGE_ACTIVE if is_carelon_email(users.email_of(row)) else STAGE_SETUP_EMAIL


def _redirect_for_stage(stage, next_url=None):
    if stage == STAGE_SETUP_PASSWORD:
        return redirect(url_for("auth.setup_password"))
    if stage == STAGE_SETUP_EMAIL:
        return redirect(url_for("auth.setup_email"))
    return redirect(next_url or url_for("main.programs"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    auth = current_auth()
    if auth and request.method == "GET":
        return _redirect_for_stage(auth["stage"])

    portal = request.values.get("portal")
    portal = portal if portal in (PORTAL_ASSOCIATE, PORTAL_ADMIN) else PORTAL_ASSOCIATE
    username = request.form.get("username", "").strip()

    if request.method == "POST":
        password = request.form.get("password", "")
        error = None
        if not username or not password:
            error = "Please enter your username and password."
        else:
            try:
                row = users.get_by_domain(username)
                stage = _authenticate(row, password) if row else None
                if stage is None:
                    error = INVALID_CREDENTIALS
                elif not role_allowed_for_portal(users.role_of(row), portal):
                    error = UNAUTHORIZED[portal]
                else:
                    start_session(row, portal, stage)
                    return _redirect_for_stage(stage, _safe_next(request.args.get("next")))
            except SupabaseError as exc:
                log.error("Login failed for lookup: %s", exc)
                error = SERVICE_DOWN
        flash(error, "error")

    return render_template("auth/login.html", portal=portal, username=username)


@bp.route("/setup/password", methods=["GET", "POST"])
@setup_required(STAGE_SETUP_PASSWORD)
def setup_password():
    if request.method == "POST":
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        problems = password_errors(new)
        if problems:
            flash("Password must contain " + ", ".join(problems) + ".", "error")
        elif new != confirm:
            flash("Passwords do not match.", "error")
        elif matches_temporary(users.password_of(g.user_row), new):
            flash("Your new password must be different from the temporary password.", "error")
        else:
            domain = users.domain_of(g.user_row)
            try:
                supabase.admin_upsert_user(users.auth_user_id(domain), users.auth_email(domain), new,
                                           {"domain": domain, "role": g.role})
                users.update(domain, {users.col(g.user_row, Config.COL_PASSWORD): hash_password(new)})
            except (SupabaseError, RuntimeError) as exc:
                log.error("Password setup failed: %s", exc)
                flash("We could not save your password. Please try again.", "error")
            else:
                set_stage(STAGE_SETUP_EMAIL)
                return redirect(url_for("auth.setup_email"))
    return render_template("auth/setup_password.html", step=1)


@bp.route("/setup/email", methods=["GET", "POST"])
@setup_required(STAGE_SETUP_EMAIL)
def setup_email():
    email = request.form.get("email", users.email_of(g.user_row)).strip().lower()
    if request.method == "POST":
        if not is_carelon_email(email):
            flash("Please enter a valid company email address.", "error")
        else:
            domain = users.domain_of(g.user_row)
            try:
                users.update(domain, {users.col(g.user_row, Config.COL_EMAIL): email})
            except (SupabaseError, RuntimeError) as exc:
                log.error("Email setup failed: %s", exc)
                flash("We could not save your email address. Please try again.", "error")
            else:
                try:
                    supabase.admin_update_user(users.auth_user_id(domain),
                                               {"user_metadata": {"domain": domain, "role": g.role,
                                                                  "carelon_email": email}})
                except SupabaseError as exc:
                    log.warning("Auth metadata sync failed: %s", exc)
                set_stage(STAGE_ACTIVE)
                session["account_created"] = True
                return redirect(url_for("auth.setup_complete"))
    return render_template("auth/setup_email.html", step=2, email=email)


@bp.route("/setup/complete")
def setup_complete():
    auth = current_auth()
    if not auth or auth["stage"] != STAGE_ACTIVE or not session.pop("account_created", False):
        return redirect(url_for("main.programs"))
    return render_template("auth/complete.html", step=3)


@bp.route("/logout", methods=["POST"])
def logout():
    end_session()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))
