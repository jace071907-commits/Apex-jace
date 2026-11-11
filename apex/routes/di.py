"""DISPUTES AND INTAKES module: Task Entry, Update Pends, Reviewed Pends, My Dashboard."""
import logging

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .. import pends, users
from ..security import login_required
from ..supabase import SupabaseError
from . import enterprise_views

bp = Blueprint("di", __name__, url_prefix="/di")
log = logging.getLogger(__name__)
PROGRAM = "di"
DB_ERROR = "The Pend database could not be reached. Please try again."


def _domain():
    return users.domain_of(g.user_row)


def _filters():
    args = request.args
    return {k: (args.get(k) or "").strip() for k in ("q", "from", "to", "status", "review")}


# ---------------- Tab 1: Task Entry ----------------
@bp.route("/task-entry", methods=["GET", "POST"])
@login_required("di.task_entry", program=PROGRAM)
def task_entry():
    form = request.form if request.method == "POST" else {}
    if request.method == "POST":
        try:
            record = pends.create(g.user_row, g.profile_map, request.form)
        except pends.PendError as exc:
            flash(str(exc), "error")
        except SupabaseError as exc:
            log.error("Pend insert failed: %s", exc)
            flash(DB_ERROR, "error")
        else:
            flash(f"Pend saved for Inquiry {record.get('INQUIRY_NUMBER')}.", "success")
            return redirect(url_for("di.task_entry"))
    return render_template("di/task_entry.html", form=form)


# ---------------- Tab 2: Update Pends ----------------
@bp.route("/update-pends")
@login_required("di.update_pends", program=PROGRAM)
def update_pends():
    f = _filters()
    rows, selected, error = [], None, None
    try:
        rows = pends.list_for(_domain(), f["q"], f["from"], f["to"], f["status"])
        if request.args.get("id"):
            selected = pends.get_for(_domain(), request.args["id"])
            if not selected:
                flash("Record not found.", "error")
    except SupabaseError as exc:
        log.error("Pend list failed: %s", exc)
        error = DB_ERROR
    return render_template("di/update_pends.html", rows=rows, selected=selected, filters=f, error=error,
                           statuses=pends.STATUSES)


@bp.route("/update-pends/<pend_id>", methods=["POST"])
@login_required("di.update_pends", program=PROGRAM)
def update_pend(pend_id):
    back = {k: v for k, v in _filters().items() if v}
    try:
        if not pends.get_for(_domain(), pend_id):
            raise pends.PendError("Record not found.")
        record = pends.update_for(_domain(), pend_id, request.form)
    except pends.PendError as exc:
        flash(str(exc), "error")
        return redirect(url_for("di.update_pends", id=pend_id, **back))
    except SupabaseError as exc:
        log.error("Pend update failed: %s", exc)
        flash(DB_ERROR, "error")
        return redirect(url_for("di.update_pends", id=pend_id, **back))
    flash(f"Inquiry {record.get('INQUIRY_NUMBER')} updated.", "success")
    return redirect(url_for("di.update_pends", id=pend_id, **back))


# ---------------- Tab 3: Reviewed Pends ----------------
@bp.route("/reviewed-pends")
@login_required("di.reviewed_pends", program=PROGRAM)
def reviewed_pends():
    f = _filters()
    review = f["review"] if f["review"] in ("Valid", "Invalid", "unacknowledged") else "reviewed"
    rows, error = [], None
    try:
        rows = pends.list_for(_domain(), f["q"], review=review)
    except SupabaseError as exc:
        log.error("Reviewed list failed: %s", exc)
        error = DB_ERROR
    return render_template("di/reviewed_pends.html", rows=rows, filters=f, error=error)


@bp.route("/reviewed-pends/<pend_id>/acknowledge", methods=["POST"])
@login_required("di.reviewed_pends", program=PROGRAM)
def acknowledge(pend_id):
    try:
        record = pends.acknowledge(_domain(), pend_id)
        flash(f"Review for Inquiry {record.get('INQUIRY_NUMBER')} acknowledged.", "success")
    except pends.PendError as exc:
        flash(str(exc), "error")
    except SupabaseError as exc:
        log.error("Acknowledge failed: %s", exc)
        flash(DB_ERROR, "error")
    back = {k: v for k, v in _filters().items() if v}
    return redirect(url_for("di.reviewed_pends", **back))


# ---------------- Sidebar: Dashboard (enterprise view of the entire Pend table) ----------------
@bp.route("/dashboards")
@login_required("di.dashboards", program=PROGRAM)
def dashboards():
    return enterprise_views.page("di.dashboards", "di.dashboards_export")


@bp.route("/dashboards/export")
@login_required("di.dashboards", program=PROGRAM)
def dashboards_export():
    return enterprise_views.export("di.dashboards")


# ---------------- Tab 4: My Dashboard ----------------
@bp.route("/dashboard")
@login_required("di.dashboard", program=PROGRAM)
def dashboard():
    q = pends.clean_search(request.args.get("q"))
    data, records, events, error = None, [], [], None
    try:
        data = pends.dashboard(_domain())
        if q:
            records = pends.list_for(_domain(), q, limit=50)
        events = pends.history(_domain(), q, limit=100 if q else 25)
    except SupabaseError as exc:
        log.error("Dashboard failed: %s", exc)
        error = DB_ERROR
    return render_template("di/dashboard.html", data=data, records=records, events=events, q=q, error=error)
