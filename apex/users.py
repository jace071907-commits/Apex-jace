"""Repository for the employee masterlist (`User` table)."""
import re
import uuid

from .config import Config
from .supabase import column, eq, supabase

# Stable namespace so each DOMAIN always maps to the same Supabase Auth user id.
_AUTH_NAMESPACE = uuid.UUID("6f1c2a4e-9b7d-4c1a-8e3f-a9e5d0b2c7f1")

# Display label -> normalised column-name candidates (first match wins).
PROFILE_FIELDS = [
    ("Associate Name", ["associatename", "name", "employeename", "fullname", "associate"]),
    ("Employee Number", ["employeenumber", "employeeno", "empno", "employeeid", "empid", "employeenum", "eid"]),
    ("Domain", ["domain"]),
    ("Role", ["role"]),
    ("Program", ["program", "lob"]),
    ("AM", ["am", "accountmanager"]),
    ("Manager Name", ["managername", "manager", "supervisor", "immediatesupervisor"]),
    ("OM", ["om", "operationsmanager"]),
    ("Email Address", ["emailaddress", "email"]),
]

SENSITIVE = {"password"}


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def resolve(row, candidates):
    """Return the actual column name in `row` that matches one of the normalised candidates."""
    keys = {_norm(k): k for k in row}
    return next((keys[c] for c in candidates if c in keys), None)


def value(row, column_name):
    raw = row.get(column_name)
    return "" if raw is None else str(raw).strip()


def profile(row):
    """Ordered list of (label, value) for the profile card, using real column values."""
    fields = []
    for label, candidates in PROFILE_FIELDS:
        col = resolve(row, candidates)
        fields.append((label, value(row, col) if col else ""))
    return fields


def public_columns(row):
    return [k for k in row if _norm(k) not in SENSITIVE]


def auth_user_id(domain):
    return str(uuid.uuid5(_AUTH_NAMESPACE, domain.strip().lower()))


def auth_email(domain):
    local = re.sub(r"[^a-z0-9._-]", "-", domain.strip().lower())
    return f"{local}@{Config.AUTH_EMAIL_DOMAIN}"


def col(row, name):
    """Actual column name in `row` for a configured name, ignoring case/spacing (e.g. ROLE -> Role)."""
    if name in row:
        return name
    target = _norm(name)
    return next((k for k in row if _norm(k) == target), name)


def domain_of(row):
    return value(row, col(row, Config.COL_DOMAIN))


def role_of(row):
    return value(row, col(row, Config.COL_ROLE))


def email_of(row):
    return value(row, col(row, Config.COL_EMAIL))


def password_of(row):
    return row.get(col(row, Config.COL_PASSWORD))


def get_by_domain(domain):
    domain = (domain or "").strip()
    if not domain:
        return None
    for candidate in dict.fromkeys([domain, domain.upper(), domain.lower()]):
        rows = supabase.select(Config.USER_TABLE, {column(Config.COL_DOMAIN): eq(candidate)}, limit=2)
        if len(rows) == 1:
            return rows[0]
        if len(rows) > 1:
            return None  # ambiguous DOMAIN; refuse to authenticate
    return None


def update(domain, values):
    rows = supabase.update(Config.USER_TABLE, {column(Config.COL_DOMAIN): eq(domain)}, values)
    if len(rows) != 1:
        raise RuntimeError(f"Expected to update exactly one user row, updated {len(rows)}.")
    return rows[0]


def total_count():
    return supabase.count(Config.USER_TABLE)


def list_users(limit=1000):
    rows = supabase.select(Config.USER_TABLE, {"order": column(Config.COL_DOMAIN)}, limit=limit)
    return [{k: v for k, v in r.items() if _norm(k) not in SENSITIVE} for r in rows]
