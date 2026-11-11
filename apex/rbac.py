"""Role-based access control.

Roles come from the ROLE column. `Associate` uses the Associate portal; every other
role (SME, Supervisor, Team Lead, Manager, AM, OM, Admin, ...) uses the Admin portal.
Add new permissions here as data-entry modules are introduced.
"""

PORTAL_ASSOCIATE = "associate"
PORTAL_ADMIN = "admin"


def is_associate(role):
    return (role or "").strip().lower() == "associate"


def role_allowed_for_portal(role, portal):
    if not (role or "").strip():
        return False
    return is_associate(role) if portal == PORTAL_ASSOCIATE else portal == PORTAL_ADMIN and not is_associate(role)


def _everyone(role):
    return bool((role or "").strip())


def _elevated(role):
    return _everyone(role) and not is_associate(role)


def _associate(role):
    return is_associate(role)


PERMISSIONS = {
    "programs.select": _everyone,
    # Disputes and Intakes — Associate module
    "di.task_entry": _associate,
    "di.update_pends": _associate,
    "di.reviewed_pends": _associate,
    "di.dashboard": _associate,
    "di.dashboards": _associate,
    # Disputes and Intakes — Admin (reviewer) module
    "dia.pend_reports": _elevated,
    "dia.review": _elevated,
    "dia.reviewed": _elevated,
    "dia.dashboard": _elevated,
    "dia.dashboards": _elevated,
    "dia.export": _elevated,
    "admin.access": _elevated,
    "settings.view": _everyone,
    "profile.view": _everyone,
    "profile.edit": _everyone,
}


def can(role, permission):
    check = PERMISSIONS.get(permission)
    return bool(check and check(role))
