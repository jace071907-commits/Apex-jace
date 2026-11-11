"""Reviewer (Admin) side of Disputes and Intakes: review queue, reviews, reviewer dashboard, export data."""
import re
from collections import Counter
from datetime import timedelta

from . import dates
from .config import Config
from .pends import MAX_TEXT, REVIEWS, STATUSES, PendError, clean_search, decorate
from .supabase import column, eq, supabase

MAX_NAME = 120
VIEWS = {"daily": 30, "weekly": 12, "monthly": 12}  # default number of periods shown per view
_ID = Config.PEND_ID_COL
# Pending and not yet claimed by any reviewer.
QUEUE = {"STATUS": eq("Pending"), "or": '(REVIEWER_DOMAIN.is.null,REVIEWER_DOMAIN.eq."")'}
FILTER_COLUMNS = {"manager": "MANAGER", "assigned_to": "ASSIGNED_TO", "sub_status": "SUB_STATUS"}


def _valid_id(pend_id):
    return bool(re.fullmatch(r"[A-Za-z0-9-]{1,64}", str(pend_id or "")))


def _queue_params(filters):
    params = dict(QUEUE)
    search = clean_search(filters.get("q"))
    if search:
        params["INQUIRY_NUMBER"] = f"ilike.*{search}*"
    for key, col in FILTER_COLUMNS.items():
        if filters.get(key):
            params[col] = eq(filters[key])
    return params


def _select_all(params, select="*", cap=50000):
    rows = []
    while True:
        batch = supabase.select(Config.PEND_TABLE, {**params, "select": select, "offset": len(rows)}, limit=1000)
        rows += batch
        if len(batch) < 1000 or len(rows) >= cap:
            return rows


# ---------------- Tab 1: Pend Reports (review queue) ----------------
def queue(filters, limit=500):
    params = {**_queue_params(filters), "order": "DATE_PENDED.asc,CREATED_AT.asc"}
    return [decorate(r) for r in supabase.select(Config.PEND_TABLE, params, limit=limit)]


def queue_count():
    return supabase.count(Config.PEND_TABLE, QUEUE)


def filter_options():
    """Distinct Manager / Assigned To / Sub Status values present in the review queue."""
    rows = _select_all(QUEUE, select="MANAGER,ASSIGNED_TO,SUB_STATUS")
    return {key: sorted({(r.get(col) or "").strip() for r in rows} - {""}, key=str.lower)
            for key, col in FILTER_COLUMNS.items()}


def get_reviewable(pend_id):
    if not _valid_id(pend_id):
        return None
    rows = supabase.select(Config.PEND_TABLE, {**QUEUE, column(_ID): eq(pend_id)}, limit=1)
    return decorate(rows[0]) if rows else None


def _review_values(form, reviewer_domain):
    review = form.get("pend_review")
    remarks = (form.get("reviewer_remarks") or "").strip()
    name = " ".join((form.get("reviewer") or "").split())
    reviewed_on = dates.parse(form.get("date_reviewed"))
    if review not in REVIEWS:
        raise PendError("Please choose Valid or Invalid.")
    if not name:
        raise PendError("Reviewer Name is required.")
    if len(name) > MAX_NAME:
        raise PendError(f"Reviewer Name must be {MAX_NAME} characters or fewer.")
    if not reviewed_on:
        raise PendError("Please enter a valid Date Reviewed.")
    if reviewed_on > dates.today():
        raise PendError("Date Reviewed cannot be in the future.")
    if not remarks:
        raise PendError("Reviewer Remarks are required.")
    if len(remarks) > MAX_TEXT:
        raise PendError(f"Reviewer Remarks must be {MAX_TEXT} characters or fewer.")
    return {"PEND_REVIEW": review, "REVIEWER": name, "REVIEWER_DOMAIN": reviewer_domain,
            "DATE_REVIEWED": reviewed_on.isoformat(), "REVIEWER_REMARKS": remarks}


def submit(pend_id, reviewer_domain, form):
    """Save a first review. Only succeeds while the pend is still Pending and unclaimed (no double reviews)."""
    values = _review_values(form, reviewer_domain)
    if not _valid_id(pend_id):
        raise PendError("Record not found.")
    rows = supabase.update(Config.PEND_TABLE, {**QUEUE, column(_ID): eq(pend_id)}, values)
    if not rows:
        raise PendError("This pend was already reviewed or is no longer Pending.")
    return decorate(rows[0])


# ---------------- Tab 2: Reviewed Pends ----------------
def _mine(reviewer_domain):
    return {"REVIEWER_DOMAIN": eq(reviewer_domain)}


def _mine_open(reviewer_domain):
    """My reviews whose pend is not Completed (a blank STATUS counts as not completed)."""
    return {**_mine(reviewer_domain), "or": '(STATUS.is.null,STATUS.neq."Completed")'}


def reviewed(reviewer_domain, search=None, review=None, limit=500):
    params = {**_mine_open(reviewer_domain), "order": "DATE_REVIEWED.desc,UPDATED_AT.desc"}
    search = clean_search(search)
    if search:
        params["INQUIRY_NUMBER"] = f"ilike.*{search}*"
    if review in REVIEWS:
        params["PEND_REVIEW"] = eq(review)
    return [decorate(r) for r in supabase.select(Config.PEND_TABLE, params, limit=limit)]


def get_reviewed(reviewer_domain, pend_id):
    if not _valid_id(pend_id):
        return None
    rows = supabase.select(Config.PEND_TABLE, {**_mine_open(reviewer_domain), column(_ID): eq(pend_id)}, limit=1)
    return decorate(rows[0]) if rows else None


def status_options(current):
    """Statuses a reviewer can choose; keeps a non-standard current value (e.g. set by another tool) selectable."""
    return STATUSES + ([current] if current and current not in STATUSES else [])


def edit(pend_id, reviewer_domain, form):
    """Update STATUS, PEND_REVIEW and REVIEWER_REMARKS. Reviewer name and Date Reviewed are kept as-is."""
    if not _valid_id(pend_id):
        raise PendError("Record not found.")
    current = get_reviewed(reviewer_domain, pend_id)
    if not current:
        raise PendError("Review not found or the pend is already Completed.")
    status = form.get("status")
    review = form.get("pend_review")
    remarks = (form.get("reviewer_remarks") or "").strip()
    if status not in status_options(current.get("STATUS")):
        raise PendError("Please choose a valid status.")
    if review not in REVIEWS:
        raise PendError("Please choose Valid or Invalid.")
    if not remarks:
        raise PendError("Reviewer Remarks are required.")
    if len(remarks) > MAX_TEXT:
        raise PendError(f"Reviewer Remarks must be {MAX_TEXT} characters or fewer.")
    values = {"STATUS": status, "PEND_REVIEW": review, "REVIEWER_REMARKS": remarks, "UPDATED_BY": reviewer_domain}
    rows = supabase.update(Config.PEND_TABLE, {**_mine_open(reviewer_domain), column(_ID): eq(pend_id)}, values)
    if not rows:
        raise PendError("Review not found or the pend is already Completed.")
    return decorate(rows[0])


# ---------------- Tab 3: My Dashboard ----------------
def _bucket(d, view):
    if view == "monthly":
        return d.replace(day=1)
    if view == "weekly":
        return d - timedelta(days=d.weekday())
    return d


def _periods(start, end, view):
    out, cur = [], _bucket(start, view)
    while cur <= end:
        out.append(cur)
        if view == "monthly":
            cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        else:
            cur += timedelta(days=7 if view == "weekly" else 1)
    return out


def _label(d, view):
    if view == "monthly":
        return d.strftime("%b %y")
    return ("Wk " if view == "weekly" else "") + d.strftime("%b %d")


def default_range(view):
    end = dates.today()
    n = VIEWS[view]
    if view == "monthly":
        start = end.replace(day=1)
        for _ in range(n - 1):
            start = (start - timedelta(days=1)).replace(day=1)
    else:
        start = _bucket(end, view) - timedelta(days=(n - 1) * (7 if view == "weekly" else 1))
    return start, end


def dashboard(reviewer_domain, view="daily", date_from=None, date_to=None):
    view = view if view in VIEWS else "daily"
    start, end = default_range(view)
    start = dates.parse(date_from) or start
    end = dates.parse(date_to) or end
    if start > end:
        start, end = end, start
    if len(_periods(start, end, view)) > 400:
        raise PendError("Date range is too large for this view. Please narrow it or choose a wider view.")

    rows = _select_all({**_mine(reviewer_domain), "DATE_REVIEWED": [f"gte.{start.isoformat()}", f"lte.{end.isoformat()}"]},
                       select="PEND_REVIEW,DATE_REVIEWED")
    review = Counter((r.get("PEND_REVIEW") or "").strip().lower() for r in rows)
    per = {}
    for r in rows:
        d = dates.parse(r.get("DATE_REVIEWED"))
        if d:
            per.setdefault(_bucket(d, view), Counter())[(r.get("PEND_REVIEW") or "").strip().lower()] += 1
    series = [{"label": _label(p, view), "valid": per.get(p, {}).get("valid", 0),
               "invalid": per.get(p, {}).get("invalid", 0)} for p in _periods(start, end, view)]
    for s in series:
        s["count"] = s["valid"] + s["invalid"]

    total = review.get("valid", 0) + review.get("invalid", 0)
    busiest = max(series, key=lambda s: s["count"]) if series else None
    return {
        "view": view, "from": start, "to": end,
        "cards": {"total": total, "valid": review.get("valid", 0), "invalid": review.get("invalid", 0),
                  "rate": round(review.get("valid", 0) * 100 / total) if total else 0},
        "summary": {"periods": len(series), "average": round(total / len(series), 1) if series else 0,
                    "busiest": busiest["label"] if busiest and busiest["count"] else "—",
                    "busiest_count": busiest["count"] if busiest else 0},
        "charts": {"review": {"valid": review.get("valid", 0), "invalid": review.get("invalid", 0)},
                   "trend": series},
    }


# ---------------- Export ----------------
def export_rows(scope, filters=None, reviewer_domain=None):
    """Raw Pend rows for Excel. scope: all | reports (filtered queue) | reviewed (my reviews, filtered)."""
    if scope == "reports":
        params = _queue_params(filters or {})
    elif scope == "reviewed":
        params = _mine(reviewer_domain)
        search = clean_search((filters or {}).get("q"))
        if search:
            params["INQUIRY_NUMBER"] = f"ilike.*{search}*"
        if (filters or {}).get("review") in REVIEWS:
            params["PEND_REVIEW"] = eq(filters["review"])
    else:
        params = {}
    return _select_all({**params, "order": "DATE_PENDED.desc"})
