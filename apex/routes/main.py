"""Program selection, profile, settings, notifications and administration."""
import logging

from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, session, url_for

from .. import notifications, preferences, programs, users
from ..config import Config
from ..security import current_auth, is_carelon_email, login_required
from ..supabase import SupabaseError, supabase

bp = Blueprint("main", __name__)
log = logging.getLogger(__name__)

# Profile fields the user may edit (label -> PROFILE_FIELDS label). Domain is the identity and stays read-only.
PROFILE_VIEW = ["Associate Name", "Employee Number", "Domain", "Program", "Manager Name", "Email Address"]
PROFILE_EDITABLE = ["Associate Name", "Employee Number", "Program", "Manager Name", "Email Address"]
PROFILE_LABELS = {"Manager Name": "Manager"}
MAX_FIELD = 120


def _domain():
    return users.domain_of(g.user_row)


@bp.route("/")
def index():
    return redirect(url_for("main.programs" if current_auth() else "auth.login"))


# ---------------- program selection ----------------
@bp.route("/programs", endpoint="programs", methods=["GET", "POST"])
@login_required("programs.select")
def programs_view():
    assigned = programs.match(g.profile_map.get("Program"))
    if request.method == "POST":
        chosen = request.form.get("program")
        if chosen not in programs.BY_KEY:
            flash("Please select a program.", "error")
        elif assigned and chosen != assigned:
            flash("You can only open the program assigned to you.", "error")
        elif not programs.is_active(chosen):
            flash(f"{programs.BY_KEY[chosen]['name']} is coming soon.", "info")
        else:
            session["program"] = chosen
            return redirect(url_for(programs.endpoint_for(chosen, g.role)))
    return render_template("main/programs.html", programs=programs.PROGRAMS, assigned=assigned,
                           is_active=programs.is_active)


# ---------------- profile ----------------
def _profile_columns():
    """Resolve the actual User-table column for each profile label."""
    labels = dict(users.PROFILE_FIELDS)
    return {label: users.resolve(g.user_row, labels[label]) for label in PROFILE_VIEW}


@bp.route("/profile")
@login_required("profile.view")
def profile():
    fields = [(PROFILE_LABELS.get(l, l), g.profile_map.get(l, "")) for l in PROFILE_VIEW]
    return render_template("main/profile.html", fields=fields)


@bp.route("/profile/edit", methods=["GET", "POST"])
@login_required("profile.edit")
def profile_edit():
    columns = _profile_columns()
    editable = [l for l in PROFILE_EDITABLE if columns.get(l)]
    values = {l: g.profile_map.get(l, "") for l in PROFILE_VIEW}
    program_names = [p["name"] for p in programs.PROGRAMS]

    if request.method == "POST":
        submitted = {l: (request.form.get(l, "") or "").strip() for l in editable}
        error = None
        if any(len(v) > MAX_FIELD for v in submitted.values()):
            error = f"Each field must be {MAX_FIELD} characters or fewer."
        elif "Associate Name" in submitted and not submitted["Associate Name"]:
            error = "Associate Name is required."
        elif "Email Address" in submitted and not is_carelon_email(submitted["Email Address"]):
            error = "Please enter a valid Carelon email address."
        elif submitted.get("Program") and submitted["Program"] not in program_names \
                and submitted["Program"] != values.get("Program"):
            error = "Please choose a valid program."
        if error:
            flash(error, "error")
            values.update(submitted)
        else:
            if "Email Address" in submitted:
                submitted["Email Address"] = submitted["Email Address"].lower()
            def changed(label, new):
                old = values.get(label) or ""
                return new.casefold() != old.casefold() if label in ("Program", "Email Address") else new != old

            changes = {columns[l]: (v or None) for l, v in submitted.items() if changed(l, v)}
            if changes:
                try:
                    users.update(_domain(), changes)
                except (SupabaseError, RuntimeError) as exc:
                    log.error("Profile update failed: %s", exc)
                    flash("We could not save your profile. Please try again.", "error")
                    values.update(submitted)
                    return render_template("main/profile_edit.html", values=values, editable=editable,
                                           program_names=program_names, labels=PROFILE_LABELS, view=PROFILE_VIEW)
                if columns.get("Program") in changes:
                    session.pop("program", None)
                if columns.get("Email Address") in changes:
                    try:
                        supabase.admin_update_user(users.auth_user_id(_domain()), {"user_metadata": {
                            "domain": _domain(), "role": g.role, "carelon_email": submitted["Email Address"]}})
                    except SupabaseError as exc:
                        log.warning("Auth metadata sync failed: %s", exc)
            flash("Profile updated." if changes else "No changes to save.", "success")
            return redirect(url_for("main.profile"))
    return render_template("main/profile_edit.html", values=values, editable=editable, program_names=program_names,
                           labels=PROFILE_LABELS, view=PROFILE_VIEW)


# ---------------- settings ----------------
def _save_prefs(values):
    prefs = preferences.clean(values, session.get("prefs"))
    preferences.save(_domain(), prefs)
    session["prefs"] = prefs
    return prefs


@bp.route("/settings", methods=["GET", "POST"])
@login_required("settings.view")
def settings():
    if request.method == "POST":
        values = request.form.to_dict()
        values["electric_border"] = "electric_border" in request.form
        try:
            _save_prefs(values)
            flash("Settings saved.", "success")
        except SupabaseError as exc:
            log.error("Settings save failed: %s", exc)
            flash("Settings could not be saved. Please try again.", "error")
        return redirect(url_for("main.settings"))
    return render_template("main/settings.html", accents=preferences.ACCENTS, modes=preferences.MODES,
                           orientations=preferences.ORIENTATIONS)


@bp.route("/api/preferences", methods=["POST"])
@login_required("settings.view")
def api_preferences():
    try:
        return jsonify(ok=True, prefs=_save_prefs(request.get_json(silent=True) or {}))
    except SupabaseError as exc:
        log.error("Preference save failed: %s", exc)
        return jsonify(ok=False), 503


# ---------------- notifications ----------------
@bp.route("/api/notifications")
@login_required()
def api_notifications():
    unread, items = notifications.inbox(_domain(), limit=8)
    return jsonify(unread=unread, items=items)


@bp.route("/api/notifications/read", methods=["POST"])
@login_required()
def api_notifications_read():
    raw = (request.get_json(silent=True) or {}).get("id")
    if raw is not None and not str(raw).isdigit():
        abort(400)
    try:
        notifications.mark_read(_domain(), raw)
    except SupabaseError as exc:
        log.error("Mark read failed: %s", exc)
        return jsonify(ok=False), 503
    return jsonify(ok=True)


@bp.route("/notifications")
@login_required()
def notification_history():
    unread, items = notifications.inbox(_domain(), limit=200)
    return render_template("main/notifications.html", unread=unread, items=items)


# ---------------- administration ----------------
@bp.route("/administration")
@login_required("admin.access")
def administration():
    rows, total, error = [], None, None
    try:
        total = users.total_count()
        rows = users.list_users()
    except SupabaseError as exc:
        log.error("Masterlist load failed: %s", exc)
        error = "The employee masterlist could not be loaded."
    columns = users.public_columns(rows[0]) if rows else []
    return render_template("main/administration.html", rows=rows, columns=columns, total=total, error=error,
                           role_col=users.col(rows[0], Config.COL_ROLE) if rows else Config.COL_ROLE)
