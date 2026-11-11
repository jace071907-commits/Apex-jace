"""Program registry. Activate a program by setting `endpoint` (Associate) / `admin_endpoint` (Admin)."""
import re

from .rbac import is_associate

PROGRAMS = [
    {"key": "di", "name": "DISPUTES AND INTAKES", "image": "di.png", "endpoint": "di.task_entry",
     "admin_endpoint": "dia.pend_reports",
     "aliases": ["disputesandintakes", "disputesintakes", "di", "dandi", "disputes", "intakes"]},
    {"key": "cob", "name": "COB", "image": "cob.png", "endpoint": None,
     "aliases": ["cob", "coordinationofbenefits"]},
    {"key": "noncob", "name": "NON COB", "image": "noncob.png", "endpoint": None,
     "aliases": ["noncob", "noncoordinationofbenefits"]},
    {"key": "cc", "name": "CASH CONTROL", "image": "cc.png", "endpoint": None, "aliases": ["cashcontrol", "cc"]},
    {"key": "iqt", "name": "IQT", "image": "iqt.png", "endpoint": None, "aliases": ["iqt"]},
    {"key": "prepay", "name": "PREPAY", "image": "prepay.png", "endpoint": None, "aliases": ["prepay", "prepayment"]},
]
BY_KEY = {p["key"]: p for p in PROGRAMS}


def _norm(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower().replace("&", "and"))


def match(program_value):
    """Map a PROGRAM column value to a program key (None when blank or unrecognised)."""
    norm = _norm(program_value)
    return next((p["key"] for p in PROGRAMS if norm and norm in p["aliases"]), None)


def is_active(key):
    return bool(BY_KEY.get(key, {}).get("endpoint"))


def endpoint_for(key, role):
    """Landing page of a program for the user's audience (Associate module vs Admin module)."""
    program = BY_KEY[key]
    return program["endpoint"] if is_associate(role) else program.get("admin_endpoint") or program["endpoint"]
