"""Repository for the Disputes and Intakes `Pend` table and its history."""
import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import dates
from .config import Config
from .supabase import SupabaseError, column, eq, supabase

log = logging.getLogger(__name__)

STATUSES = ["Pending", "Completed"]
REVIEWS = ["Valid", "Invalid"]
MAX_INQUIRY = 60
MAX_TEXT = 4000
MAX_SUB_STATUS = 100

# Display order/labels for the record detail view. PENDED_DAYS is intentionally not displayed: it is
# maintained by the database (apex_pend_before trigger + daily apex_refresh_pended_days job) for reporting.
DETAIL_FIELDS = [
    ("INQUIRY_NUMBER", "Inquiry Number"), ("STATUS", "Status"), ("SUB_STATUS", "Sub Status"),
    ("DATE_PENDED", "Date Pended"), ("ASSIGNED_TO", "Assigned To"), ("DOMAIN", "Domain"), ("MANAGER", "Manager"),
    ("REMARKS", "Remarks"), ("LAST_NOTE", "Last Note"), ("LAST_DATE_UPDATE", "Last Date Update"),
    ("PEND_REVIEW", "Pend Review"), ("REVIEWER", "Reviewer"), ("REVIEWER_DOMAIN", "Reviewer Domain"),
    ("REVIEWER_REMARKS", "Reviewer Remarks"), ("DATE_REVIEWED", "Date Reviewed"),
]
_DATE_FIELDS = {"DATE_PENDED", "LAST_DATE_UPDATE", "DATE_REVIEWED"}
_ID = Config.PEND_ID_COL


class PendError(Exception):
    """Validation error shown to the user."""


def clean_search(value):
    """Allow only characters that are safe inside a PostgREST ilike filter."""
    return re.sub(r"[^A-Za-z0-9 _\-/#]", "", (value or "")).strip()[:MAX_INQUIRY]


def _norm(value):
    return str(value or "").strip().lower()


def decorate(row):
    """Add computed/display values."""
    row = dict(row)
    row["_id"] = str(row.get(_ID, ""))
    row["_status"] = _norm(row.get("STATUS"))
    row["_review"] = _norm(row.get("PEND_REVIEW"))
    row["_needs_ack"] = row["_review"] == "invalid" and not row.get("ACKNOWLEDGED")
    row["_details"] = [(label, dates.display(row.get(k)) if k in _DATE_FIELDS else row.get(k)) for k, label in DETAIL_FIELDS]
    return row


def _owner(domain):
    return {"DOMAIN": eq(domain)}


def _sub_status(form):
    value = " ".join((form.get("sub_status") or "").split())
    if len(value) > MAX_SUB_STATUS:
        raise PendError(f"Sub Status must be {MAX_SUB_STATUS} characters or fewer.")
    return value or None


def list_for(domain, search=None, date_from=None, date_to=None, status=None, review=None, limit=500):
    params = {**_owner(domain), "order": "DATE_PENDED.desc,CREATED_AT.desc"}
    search = clean_search(search)
    if search:
        params["INQUIRY_NUMBER"] = f"ilike.*{search}*"
    date_filters = [f"gte.{d.isoformat()}" for d in [dates.parse(date_from)] if d]
    date_filters += [f"lte.{d.isoformat()}" for d in [dates.parse(date_to)] if d]
    if date_filters:
        params["DATE_PENDED"] = date_filters
    if status in STATUSES:
        params["STATUS"] = eq(status)
    if review == "reviewed":
        params["PEND_REVIEW"] = "not.is.null"
    elif review in REVIEWS:
        params["PEND_REVIEW"] = eq(review)
    elif review == "unacknowledged":
        params["PEND_REVIEW"] = eq("Invalid")
        params["ACKNOWLEDGED"] = "is.false"
    return [decorate(r) for r in supabase.select(Config.PEND_TABLE, params, limit=limit)]


def get_for(domain, pend_id):
    if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", str(pend_id or "")):
        return None
    rows = supabase.select(Config.PEND_TABLE, {**_owner(domain), column(_ID): eq(pend_id)}, limit=1)
    return decorate(rows[0]) if rows else None


def create(user_row, profile_map, form):
    inquiry = (form.get("inquiry_number") or "").strip()
    remarks = (form.get("remarks") or "").strip()
    date_pended = dates.parse(form.get("date_pended")) or dates.today()
    if not inquiry:
        raise PendError("Inquiry Number is required.")
    if len(inquiry) > MAX_INQUIRY or not re.fullmatch(r"[A-Za-z0-9 _\-/#]+", inquiry):
        raise PendError("Inquiry Number may only contain letters, numbers, spaces, - _ / #.")
    if date_pended > dates.today():
        raise PendError("Date Pended cannot be in the future.")
    if len(remarks) > MAX_TEXT:
        raise PendError(f"Remarks must be {MAX_TEXT} characters or fewer.")

    domain = profile_map.get("Domain")
    record = {
        "STATUS": "Pending",
        "SUB_STATUS": _sub_status(form),
        "REMARKS": remarks or None,
        "INQUIRY_NUMBER": inquiry,
        "DATE_PENDED": date_pended.isoformat(),
        "ASSIGNED_TO": profile_map.get("Associate Name") or domain,
        "DOMAIN": domain,
        "MANAGER": profile_map.get("Manager Name") or None,
        "PENDED_DAYS": (dates.today() - date_pended).days,
        "UPDATED_BY": domain,
    }
    return decorate(supabase.insert(Config.PEND_TABLE, record)[0])


def update_for(domain, pend_id, form):
    status = form.get("status")
    note = (form.get("last_note") or "").strip()
    if status not in STATUSES:
        raise PendError("Please choose a valid status.")
    if len(note) > MAX_TEXT:
        raise PendError(f"Last Note must be {MAX_TEXT} characters or fewer.")
    values = {"STATUS": status, "SUB_STATUS": _sub_status(form), "LAST_NOTE": note or None,
              "LAST_DATE_UPDATE": dates.today().isoformat(), "UPDATED_BY": domain}
    rows = supabase.update(Config.PEND_TABLE, {**_owner(domain), column(_ID): eq(pend_id)}, values)
    if not rows:
        raise PendError("Record not found.")
    return decorate(rows[0])


def acknowledge(domain, pend_id):
    params = {**_owner(domain), column(_ID): eq(pend_id), "PEND_REVIEW": eq("Invalid"), "ACKNOWLEDGED": "is.false"}
    values = {"ACKNOWLEDGED": True, "ACKNOWLEDGED_BY": domain,
              "ACKNOWLEDGED_AT": datetime.now(timezone.utc).isoformat(), "UPDATED_BY": domain}
    rows = supabase.update(Config.PEND_TABLE, params, values)
    if not rows:
        raise PendError("This review was already acknowledged or does not require acknowledgement.")
    return decorate(rows[0])


def unacknowledged_count(domain):
    try:
        return supabase.count(Config.PEND_TABLE, {**_owner(domain), "PEND_REVIEW": eq("Invalid"),
                                                  "ACKNOWLEDGED": "is.false"})
    except SupabaseError as exc:
        log.warning("Unacknowledged count unavailable: %s", exc)
        return 0


def _all_for(domain):
    rows, page = [], 1000
    while True:
        batch = supabase.select(Config.PEND_TABLE, {**_owner(domain), "select": "STATUS,PEND_REVIEW,DATE_PENDED",
                                                    "offset": len(rows)}, limit=page)
        rows += batch
        if len(batch) < page or len(rows) >= 20000:
            return rows


def dashboard(domain):
    rows = _all_for(domain)
    status = Counter(_norm(r.get("STATUS")) for r in rows)
    review = Counter(_norm(r.get("PEND_REVIEW")) for r in rows)
    pended = [d for d in (dates.parse(r.get("DATE_PENDED")) for r in rows) if d]

    today = dates.today()
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    months = []
    y, m = today.year, today.month
    for _ in range(12):
        months.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    by_month = Counter((d.year, d.month) for d in pended)
    by_day = Counter(pended)
    start = today - timedelta(days=29)

    return {
        "cards": {
            "total": len(rows),
            "pending": status.get("pending", 0),
            "completed": status.get("completed", 0),
            "valid": review.get("valid", 0),
            "invalid": review.get("invalid", 0),
        },
        "charts": {
            "review": {"valid": review.get("valid", 0), "invalid": review.get("invalid", 0),
                       "unreviewed": len(rows) - review.get("valid", 0) - review.get("invalid", 0)},
            "monthly": [{"label": f"{month_names[mo - 1]} {str(yr)[2:]}", "count": by_month.get((yr, mo), 0)}
                        for yr, mo in reversed(months)],
            "daily": [{"label": (start + timedelta(days=i)).strftime("%b %d"),
                       "count": by_day.get(start + timedelta(days=i), 0)} for i in range(30)],
        },
    }


def history(domain, search=None, limit=60):
    """Pend history events for the user. Falls back to an empty list if the history table is missing."""
    params = {"domain": eq(domain), "order": "created_at.desc"}
    search = clean_search(search)
    if search:
        params["inquiry_number"] = f"ilike.*{search}*"
    try:
        return supabase.select(Config.HISTORY_TABLE, params, limit=limit)
    except SupabaseError as exc:
        log.warning("Pend history unavailable: %s", exc)
        return []
