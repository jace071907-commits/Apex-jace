"""Enterprise (executive) dashboard over the ENTIRE Pend table — not scoped to the logged-in user.

Shared by the Associate and Admin "Dashboard" menu. Filters are applied in the database; KPIs, manager
analytics, charts and the report table are computed from the same filtered rows so everything stays consistent.
"""
import math
from collections import Counter
from datetime import timedelta

from . import dates
from .reviews import _select_all
from .supabase import eq

PAGE_SIZE = 25
MAX_TREND_DAYS = 92
UNASSIGNED = "(No manager)"
COLUMNS = ("id,INQUIRY_NUMBER,STATUS,REMARKS,ASSIGNED_TO,SUB_STATUS,MANAGER,PEND_REVIEW,REVIEWER,"
           "REVIEWER_REMARKS,DATE_REVIEWED,DATE_PENDED")
REPORT_COLUMNS = [
    ("INQUIRY_NUMBER", "Inquiry Number"), ("STATUS", "Status"), ("REMARKS", "Remarks"), ("ASSIGNED_TO", "Assigned To"),
    ("SUB_STATUS", "Sub Status"), ("MANAGER", "Manager"), ("PEND_REVIEW", "Pend Review"), ("REVIEWER", "Reviewer"),
    ("REVIEWER_REMARKS", "Reviewer Remarks"), ("DATE_REVIEWED", "Date Reviewed"),
]
SORTABLE = {key for key, _ in REPORT_COLUMNS}
FILTER_COLUMNS = {"manager": "MANAGER", "assigned_to": "ASSIGNED_TO", "sub_status": "SUB_STATUS"}
STATUS_COLORS = {"pending": "#f97316", "completed": "#22c55e", "open": "#3b82f6", "in progress": "#a855f7"}


def _norm(value):
    return str(value or "").strip().lower()


def parse_filters(args):
    f = {k: (args.get(k) or "").strip()[:120] for k in FILTER_COLUMNS}
    f["from"] = dates.parse(args.get("from"))
    f["to"] = dates.parse(args.get("to"))
    if f["from"] and f["to"] and f["from"] > f["to"]:
        f["from"], f["to"] = f["to"], f["from"]
    f["q"] = " ".join((args.get("q") or "").split())[:100]
    f["sort"] = args.get("sort") if args.get("sort") in SORTABLE else "DATE_REVIEWED"
    f["dir"] = "asc" if args.get("dir") == "asc" else "desc"
    try:
        f["page"] = max(int(args.get("page") or 1), 1)
    except ValueError:
        f["page"] = 1
    return f


def query_args(f, **overrides):
    """URL query parameters for the current filters (used for links, sorting, paging and export)."""
    out = {k: f[k] for k in FILTER_COLUMNS if f.get(k)}
    out.update({k: f[k].isoformat() for k in ("from", "to") if f.get(k)})
    if f.get("q"):
        out["q"] = f["q"]
    out.update({"sort": f["sort"], "dir": f["dir"]})
    out.update(overrides)
    return {k: v for k, v in out.items() if v not in (None, "")}


def has_filters(f):
    return any(f.get(k) for k in (*FILTER_COLUMNS, "from", "to", "q"))


def _params(f):
    params = {col: eq(f[key]) for key, col in FILTER_COLUMNS.items() if f.get(key)}
    date_filters = [f"gte.{f['from'].isoformat()}"] if f.get("from") else []
    date_filters += [f"lte.{f['to'].isoformat()}"] if f.get("to") else []
    if date_filters:
        params["DATE_PENDED"] = date_filters
    return params


def _search(rows, q):
    if not q:
        return rows
    needle = q.lower()
    keys = [k for k, _ in REPORT_COLUMNS] + ["DATE_PENDED"]
    return [r for r in rows if any(needle in str(r.get(k) or "").lower() for k in keys)]


def filtered_rows(f, select=COLUMNS):
    return _search(_select_all({**_params(f), "order": "DATE_PENDED.desc"}, select=select), f.get("q"))


def all_rows():
    return _select_all({"order": "DATE_PENDED.desc"})


def filter_options():
    rows = _select_all({}, select="MANAGER,ASSIGNED_TO,SUB_STATUS")
    return {key: sorted({(r.get(col) or "").strip() for r in rows} - {""}, key=str.lower)
            for key, col in FILTER_COLUMNS.items()}


def _sorted(rows, key, direction):
    filled = [r for r in rows if r.get(key) not in (None, "")]
    empty = [r for r in rows if r.get(key) in (None, "")]
    filled.sort(key=lambda r: str(r.get(key)).lower(), reverse=direction == "desc")
    return filled + empty  # blanks always last


def _trend(rows, f):
    end = f.get("to") or dates.today()
    start = f["from"] if f.get("from") and (end - f["from"]).days < MAX_TREND_DAYS else end - timedelta(days=29)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    per = {}
    for r in rows:
        d = dates.parse(r.get("DATE_REVIEWED"))
        if d and start <= d <= end:
            per.setdefault(d, Counter())[_norm(r.get("PEND_REVIEW"))] += 1
    return [{"label": d.strftime("%b %d"), "valid": per.get(d, {}).get("valid", 0),
             "invalid": per.get(d, {}).get("invalid", 0),
             "count": per.get(d, {}).get("valid", 0) + per.get(d, {}).get("invalid", 0)} for d in days], start, end


def build(f):
    rows = filtered_rows(f)
    status = Counter(_norm(r.get("STATUS")) for r in rows)
    review = Counter(_norm(r.get("PEND_REVIEW")) for r in rows)
    total = len(rows)

    managers = {}
    for r in rows:
        m = managers.setdefault((r.get("MANAGER") or "").strip() or UNASSIGNED,
                                {"pending": 0, "completed": 0, "valid": 0, "invalid": 0, "total": 0})
        m["total"] += 1
        st, rv = _norm(r.get("STATUS")), _norm(r.get("PEND_REVIEW"))
        if st in ("pending", "completed"):
            m[st] += 1
        if rv in ("valid", "invalid"):
            m[rv] += 1
    manager_list = sorted(({"name": k, **v} for k, v in managers.items()), key=lambda m: (-m["total"], m["name"].lower()))
    for m in manager_list:
        reviewed = m["valid"] + m["invalid"]
        m["completion"] = round(m["completed"] * 100 / m["total"]) if m["total"] else 0
        m["valid_rate"] = round(m["valid"] * 100 / reviewed) if reviewed else None

    distribution = []
    for key, n in status.most_common():
        label = next((r.get("STATUS").strip() for r in rows if _norm(r.get("STATUS")) == key), "") or "No status"
        distribution.append({"label": label, "value": n, "color": STATUS_COLORS.get(key, "#94a3b8")})

    trend, trend_start, trend_end = _trend(rows, f)

    ordered = _sorted(rows, f["sort"], f["dir"])
    pages = max(math.ceil(total / PAGE_SIZE), 1)
    page = min(f["page"], pages)
    report = ordered[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]

    pct = lambda n: round(n * 100 / total) if total else 0  # noqa: E731
    return {
        "total": total,
        "cards": {
            "pending": {"value": status.get("pending", 0), "share": pct(status.get("pending", 0))},
            "completed": {"value": status.get("completed", 0), "share": pct(status.get("completed", 0))},
            "valid": {"value": review.get("valid", 0), "share": pct(review.get("valid", 0))},
            "invalid": {"value": review.get("invalid", 0), "share": pct(review.get("invalid", 0))},
        },
        "managers": manager_list,
        "charts": {
            "status_split": [{"label": "Pending", "value": status.get("pending", 0), "color": "#f97316"},
                             {"label": "Completed", "value": status.get("completed", 0), "color": "#22c55e"}],
            "review_split": [{"label": "Valid", "value": review.get("valid", 0), "color": "#10b981"},
                             {"label": "Invalid", "value": review.get("invalid", 0), "color": "#ef4444"}],
            "distribution": distribution,
            "managers": [{"label": m["name"], "pending": m["pending"], "completed": m["completed"],
                          "valid": m["valid"], "invalid": m["invalid"]} for m in manager_list[:12]],
            "trend": trend,
        },
        "trend_range": (trend_start, trend_end),
        "report": report,
        "page": page,
        "pages": pages,
    }
