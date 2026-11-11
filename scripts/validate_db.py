"""Validate the Supabase connection and the `User` table before running APEX.

Usage:  python scripts/validate_db.py
Never prints password values.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apex import programs, users  # noqa: E402
from apex.config import Config  # noqa: E402
from apex.security import is_carelon_email, is_hashed  # noqa: E402
from apex.supabase import SupabaseError, supabase  # noqa: E402

OK, FAIL, WARN = "[ OK ]", "[FAIL]", "[WARN]"
REQUIRED_PEND_COLUMNS = [
    "STATUS", "REMARKS", "INQUIRY_NUMBER", "DATE_PENDED", "ASSIGNED_TO", "DOMAIN", "MANAGER", "PENDED_DAYS",
    "LAST_NOTE", "LAST_DATE_UPDATE", "PEND_REVIEW", "REVIEWER", "REVIEWER_REMARKS", "DATE_REVIEWED",
    "ACKNOWLEDGED", "ACKNOWLEDGED_BY", "ACKNOWLEDGED_AT", "UPDATED_BY", "CREATED_AT", "UPDATED_AT",
    "REVIEWER_DOMAIN", "SUB_STATUS",
]


def main():
    missing = Config.missing()
    if missing:
        print(FAIL, "Missing environment variables:", ", ".join(missing))
        return 1
    print(OK, "Environment configured for", Config.SUPABASE_URL)

    try:
        total = supabase.count(Config.USER_TABLE)
    except SupabaseError as exc:
        print(FAIL, f"Cannot read table '{Config.USER_TABLE}':", exc)
        return 1
    print(OK, f"Connected. Table '{Config.USER_TABLE}' exists with {total} row(s).")

    rows = []
    while len(rows) < total:
        batch = supabase.select(Config.USER_TABLE, {"offset": len(rows)}, limit=1000)
        if not batch:
            break
        rows += batch
    if not rows:
        print(WARN, "Table is empty; no users can sign in yet.")
        return 0

    columns = list(rows[0].keys())
    print(OK, f"{len(columns)} column(s):", ", ".join(columns))

    status = 0
    for label, name in [("Username", Config.COL_DOMAIN), ("Password", Config.COL_PASSWORD),
                        ("Role", Config.COL_ROLE), ("Email", Config.COL_EMAIL)]:
        actual = users.col(rows[0], name)
        if actual in columns:
            print(OK, f"{label} column -> '{actual}'" + (f" (configured as '{name}')" if actual != name else ""))
        else:
            print(FAIL, f"{label} column '{name}' not found. Set APEX_COL_{label.upper() if label != 'Username' else 'DOMAIN'}.")
            status = 1

    print("\nProfile field mapping:")
    for label, candidates in users.PROFILE_FIELDS:
        col = users.resolve(rows[0], candidates)
        print(" ", OK if col else WARN, f"{label:<16} -> {col or 'NOT FOUND'}")

    if status:
        return status

    domains = Counter(users.domain_of(r).lower() for r in rows)
    dupes = [d for d, n in domains.items() if n > 1]
    blank = domains.get("", 0)
    print("\nData checks:")
    print(" ", WARN if dupes else OK, f"Duplicate DOMAIN values: {len(dupes)}" + (" (these users cannot sign in)" if dupes else ""))
    print(" ", WARN if blank else OK, f"Blank DOMAIN values: {blank}")
    roles = Counter(users.role_of(r) or "(blank)" for r in rows)
    print(" ", OK, "Roles:", ", ".join(f"{k}={v}" for k, v in roles.most_common()))
    hashed = sum(is_hashed(users.password_of(r)) for r in rows)
    print(" ", OK, f"Accounts set up: {hashed}; pending first-time login: {len(rows) - hashed}")
    emails = sum(is_carelon_email(users.email_of(r)) for r in rows)
    print(" ", OK, f"Registered Carelon emails: {emails}")

    try:
        supabase.admin_update_user("00000000-0000-0000-0000-000000000000", {})
    except SupabaseError as exc:
        if exc.status == 404:
            print(" ", OK, "Supabase Auth admin API reachable.")
        else:
            print(" ", FAIL, "Supabase Auth admin API:", exc)
            status = 1

    print("\nPrograms (PROGRAM column):")
    program_col = users.resolve(rows[0], dict(users.PROFILE_FIELDS)["Program"])
    for value, n in Counter(users.value(r, program_col) or "(blank)" for r in rows).most_common():
        key = programs.match(value)
        print(" ", OK if key or value == "(blank)" else WARN, f"{value!r} x{n} -> {key or ('select any' if value == '(blank)' else 'UNRECOGNISED')}")

    print("\nDisputes and Intakes tables:")
    return _check_module_tables() or status


def _check_module_tables():
    status = 0
    try:
        pend_total = supabase.count(Config.PEND_TABLE)
        sample = supabase.select(Config.PEND_TABLE, limit=1)
    except SupabaseError as exc:
        print(" ", FAIL, f"Table '{Config.PEND_TABLE}':", exc)
        return 1
    print(" ", OK, f"'{Config.PEND_TABLE}' reachable with {pend_total} row(s).")
    if sample:
        cols = set(sample[0])
        print(" ", OK, "Columns:", ", ".join(sample[0]))
        missing = [c for c in [Config.PEND_ID_COL] + REQUIRED_PEND_COLUMNS if c not in cols]
        if missing:
            print(" ", FAIL, "Missing columns (run the SQL files in supabase/migrations/ in order):", ", ".join(missing))
            status = 1
    else:
        try:
            supabase.select(Config.PEND_TABLE, {"select": ",".join([Config.PEND_ID_COL] + REQUIRED_PEND_COLUMNS)}, limit=1)
            print(" ", OK, "All required Pend columns exist (table is empty).")
        except SupabaseError as exc:
            print(" ", FAIL, "Pend columns incomplete (run the SQL migration):", exc.message)
            status = 1
    for table in (Config.HISTORY_TABLE, Config.NOTIFICATION_TABLE, Config.SETTINGS_TABLE):
        try:
            print(" ", OK, f"'{table}' reachable with {supabase.count(table)} row(s).")
        except SupabaseError as exc:
            print(" ", FAIL, f"'{table}' missing (run the SQL migration):", exc.message)
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
