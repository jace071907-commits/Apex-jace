"""Shared request handlers for the enterprise Dashboard menu (used by both the Associate and Admin modules)."""
import logging
import re

from flask import Response, flash, redirect, render_template, request, url_for

from .. import dates, enterprise, xlsx
from ..supabase import SupabaseError

log = logging.getLogger(__name__)
DB_ERROR = "The Pend database could not be reached. Please try again."


def page(self_endpoint, export_endpoint):
    f = enterprise.parse_filters(request.args)
    data, options, error = None, {k: [] for k in enterprise.FILTER_COLUMNS}, None
    try:
        data = enterprise.build(f)
        options = enterprise.filter_options()
    except SupabaseError as exc:
        log.error("Enterprise dashboard failed: %s", exc)
        error = DB_ERROR
    return render_template("dashboard/executive.html", data=data, f=f, options=options, error=error,
                           columns=enterprise.REPORT_COLUMNS, self_endpoint=self_endpoint,
                           export_endpoint=export_endpoint, query_args=enterprise.query_args,
                           filtered=enterprise.has_filters(f))


def export(self_endpoint):
    f = enterprise.parse_filters(request.args)
    scope = "filtered" if request.args.get("scope") == "filtered" else "all"
    try:
        rows = enterprise.filtered_rows(f, select="*") if scope == "filtered" else enterprise.all_rows()
    except SupabaseError as exc:
        log.error("Enterprise export failed: %s", exc)
        flash(DB_ERROR, "error")
        return redirect(url_for(self_endpoint, **enterprise.query_args(f)))
    headers = list(dict.fromkeys(k for r in rows for k in r))
    label = "dashboard_filtered" if scope == "filtered" and enterprise.has_filters(f) else (
        "dashboard_view" if scope == "filtered" else "all")
    filename = re.sub(r"[^A-Za-z0-9_.-]", "", f"apex_pends_{label}_{dates.today():%Y%m%d}.xlsx")
    return Response(xlsx.build(headers, rows, sheet_name="Pends"),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
