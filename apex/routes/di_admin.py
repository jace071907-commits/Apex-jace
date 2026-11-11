"""DISPUTES AND INTAKES — Admin (reviewer) module: Pend Reports, Review, Reviewed Pends, My Dashboard, Export."""
import logging
import re

from flask import Blueprint, Response, flash, g, redirect, render_template, request, url_for

from .. import dates, reviews, users, xlsx
from ..pends import REVIEWS, PendError, clean_search
from ..security import login_required
from ..supabase import SupabaseError
from . import enterprise_views

bp = Blueprint("dia", __name__, url_prefix="/di/admin")
log = logging.getLogger(__name__)
PROGRAM = "di"
DB_ERROR = "The Pend database could not be reached. Please try again."
EXPORT_SCOPES = {"all", "reports", "reviewed"}


def _me():
    return users.domain_of(g.user_row)


def _my_name():
    return g.profile_map.get("Associate Name") or _me()


def _report_filters():
    a = request.args
    return {"q": clean_search(a.get("q")), **{k: (a.get(k) or "").strip()[:120] for k in reviews.FILTER_COLUMNS}}


def _reviewed_filters():
    review = request.args.get("review")
    return {"q": clean_search(request.args.get("q")), "review": review if review in REVIEWS else ""}


def _keep(filters):
    return {k: v for k, v in filters.items() if v}


# ---------------- Tab 1: Pend Reports ----------------
@bp.route("/pend-reports")
@login_required("dia.pend_reports", program=PROGRAM)
def pend_reports():
    f = _report_filters()
    rows, options, error = [], {k: [] for k in reviews.FILTER_COLUMNS}, None
    try:
        rows = reviews.queue(f)
        options = reviews.filter_options()
    except SupabaseError as exc:
        log.error("Pend Reports failed: %s", exc)
        error = DB_ERROR
    return render_template("di_admin/pend_reports.html", rows=rows, filters=f, keep=_keep(f), options=options,
                           error=error)


@bp.route("/review/<pend_id>", methods=["GET", "POST"])
@login_required("dia.review", program=PROGRAM)
def review(pend_id):
    keep = _keep(_report_filters())
    form = request.form if request.method == "POST" else {}
    try:
        record = reviews.get_reviewable(pend_id)
        if not record:
            flash("This pend was already reviewed or is no longer Pending.", "info")
            return redirect(url_for("dia.pend_reports", **keep))
        if request.method == "POST":
            saved = reviews.submit(pend_id, _me(), request.form)
            flash(f"Review saved for Inquiry {saved.get('INQUIRY_NUMBER')} ({saved.get('PEND_REVIEW')}).", "success")
            return redirect(url_for("dia.pend_reports", **keep))
    except PendError as exc:
        flash(str(exc), "error")
        if "already reviewed" in str(exc):
            return redirect(url_for("dia.pend_reports", **keep))
    except SupabaseError as exc:
        log.error("Review failed: %s", exc)
        flash(DB_ERROR, "error")
        return redirect(url_for("dia.pend_reports", **keep))
    return render_template("di_admin/review.html", record=record, form=form, keep=keep, mode="review",
                           defaults={"reviewer": _my_name(), "domain": _me(), "date": dates.today().isoformat()},
                           cancel_url=url_for("dia.pend_reports", **keep),
                           action=url_for("dia.review", pend_id=pend_id, **keep))


# ---------------- Tab 2: Reviewed Pends ----------------
@bp.route("/reviewed")
@login_required("dia.reviewed", program=PROGRAM)
def reviewed():
    f = _reviewed_filters()
    rows, error = [], None
    try:
        rows = reviews.reviewed(_me(), f["q"], f["review"])
    except SupabaseError as exc:
        log.error("Reviewed list failed: %s", exc)
        error = DB_ERROR
    return render_template("di_admin/reviewed.html", rows=rows, filters=f, keep=_keep(f), error=error)


@bp.route("/reviewed/<pend_id>/edit", methods=["GET", "POST"])
@login_required("dia.reviewed", program=PROGRAM)
def edit_review(pend_id):
    keep = _keep(_reviewed_filters())
    form = request.form if request.method == "POST" else {}
    try:
        record = reviews.get_reviewed(_me(), pend_id)
        if not record:
            flash("Review not found.", "error")
            return redirect(url_for("dia.reviewed", **keep))
        if request.method == "POST":
            saved = reviews.edit(pend_id, _me(), request.form)
            done = (saved.get("STATUS") or "").lower() == "completed"
            flash(f"Review updated for Inquiry {saved.get('INQUIRY_NUMBER')}."
                  + (" It is now Completed and has moved out of Reviewed Pends." if done else ""), "success")
            return redirect(url_for("dia.reviewed", **keep))
    except PendError as exc:
        flash(str(exc), "error")
    except SupabaseError as exc:
        log.error("Edit review failed: %s", exc)
        flash(DB_ERROR, "error")
        return redirect(url_for("dia.reviewed", **keep))
    return render_template("di_admin/review.html", record=record, form=form, keep=keep, mode="edit",
                           defaults={"reviewer": record.get("REVIEWER") or _my_name(), "domain": _me(),
                                     "date": (dates.parse(record.get("DATE_REVIEWED")) or dates.today()).isoformat(),
                                     "review": record.get("PEND_REVIEW"), "remarks": record.get("REVIEWER_REMARKS"),
                                     "status": record.get("STATUS")},
                           status_options=reviews.status_options(record.get("STATUS")),
                           cancel_url=url_for("dia.reviewed", **keep),
                           action=url_for("dia.edit_review", pend_id=pend_id, **keep))


# ---------------- Tab 3: My Dashboard ----------------
@bp.route("/dashboard")
@login_required("dia.dashboard", program=PROGRAM)
def dashboard():
    view = request.args.get("view") if request.args.get("view") in reviews.VIEWS else "daily"
    data, error = None, None
    try:
        data = reviews.dashboard(_me(), view, request.args.get("from"), request.args.get("to"))
    except PendError as exc:
        flash(str(exc), "error")
        data = reviews.dashboard(_me(), view)
    except SupabaseError as exc:
        log.error("Reviewer dashboard failed: %s", exc)
        error = DB_ERROR
    return render_template("di_admin/dashboard.html", data=data, view=view, views=list(reviews.VIEWS), error=error)


# ---------------- Sidebar: Dashboard (enterprise view of the entire Pend table) ----------------
@bp.route("/dashboards")
@login_required("dia.dashboards", program=PROGRAM)
def dashboards():
    return enterprise_views.page("dia.dashboards", "dia.dashboards_export")


@bp.route("/dashboards/export")
@login_required("dia.dashboards", program=PROGRAM)
def dashboards_export():
    return enterprise_views.export("dia.dashboards")


# ---------------- Export to Excel (Pend table only) ----------------
@bp.route("/export")
@login_required("dia.export", program=PROGRAM)
def export():
    scope = request.args.get("scope") if request.args.get("scope") in EXPORT_SCOPES else "all"
    filters = _report_filters() if scope == "reports" else _reviewed_filters()
    try:
        rows = reviews.export_rows(scope, filters, _me())
    except SupabaseError as exc:
        log.error("Export failed: %s", exc)
        flash(DB_ERROR, "error")
        return redirect(url_for("dia.reviewed" if scope == "reviewed" else "dia.pend_reports", **_keep(filters)))
    headers = list(dict.fromkeys(k for r in rows for k in r))
    label = {"all": "all", "reports": "pend_reports", "reviewed": "my_reviews"}[scope]
    if scope != "all" and any(filters.values()):
        label += "_filtered"
    filename = re.sub(r"[^A-Za-z0-9_.-]", "", f"apex_pends_{label}_{dates.today():%Y%m%d}.xlsx")
    return Response(xlsx.build(headers, rows, sheet_name="Pends"),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
