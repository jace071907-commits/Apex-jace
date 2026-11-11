"""Sidebar and tab registries. Items are filtered by permission, so each audience
(Associate module vs Admin module) only sees its own entries."""
from .rbac import can

MODULE_NAV = {
    "di": [
        # Associate module
        {"endpoint": "di.task_entry", "label": "Task Entry", "icon": "entry", "permission": "di.task_entry"},
        {"endpoint": "di.update_pends", "label": "Update Pends", "icon": "edit", "permission": "di.update_pends"},
        {"endpoint": "di.reviewed_pends", "label": "Reviewed Pends", "icon": "shield", "permission": "di.reviewed_pends",
         "badge": "unacknowledged"},
        {"endpoint": "di.dashboards", "label": "Dashboard", "icon": "reports", "permission": "di.dashboards"},
        # Admin module
        {"endpoint": "dia.pend_reports", "label": "Pend Reports", "icon": "records", "permission": "dia.pend_reports",
         "badge": "queue", "match": ["dia.review"]},
        {"endpoint": "dia.reviewed", "label": "Reviewed Pends", "icon": "shield", "permission": "dia.reviewed",
         "match": ["dia.edit_review"]},
        {"endpoint": "dia.dashboards", "label": "Dashboard", "icon": "reports", "permission": "dia.dashboards"},
    ],
}

MODULE_TABS = {
    "di": [
        {"endpoint": "di.task_entry", "label": "Task Entry", "icon": "entry", "permission": "di.task_entry"},
        {"endpoint": "di.update_pends", "label": "Update Pends", "icon": "edit", "permission": "di.update_pends"},
        {"endpoint": "di.reviewed_pends", "label": "Reviewed Pends", "icon": "shield", "permission": "di.reviewed_pends"},
        {"endpoint": "di.dashboard", "label": "My Dashboard", "icon": "reports", "permission": "di.dashboard"},
        {"endpoint": "dia.pend_reports", "label": "Pend Reports", "icon": "records", "permission": "dia.pend_reports"},
        {"endpoint": "dia.reviewed", "label": "Reviewed Pends", "icon": "shield", "permission": "dia.reviewed"},
        {"endpoint": "dia.dashboard", "label": "My Dashboard", "icon": "reports", "permission": "dia.dashboard"},
    ],
}

COMMON_NAV = [
    {"endpoint": "main.profile", "label": "Profile", "icon": "profile", "permission": "profile.view",
     "match": ["main.profile_edit"]},
    {"endpoint": "main.settings", "label": "Settings", "icon": "settings", "permission": "settings.view"},
    {"endpoint": "main.administration", "label": "Administration", "icon": "admin", "permission": "admin.access",
     "hide_in": ["di"]},
    {"endpoint": "main.programs", "label": "Switch Program", "icon": "grid", "permission": "programs.select"},
]


def nav_for(role, program=None):
    items = MODULE_NAV.get(program, []) + COMMON_NAV
    return [item for item in items if can(role, item["permission"]) and program not in item.get("hide_in", [])]


def tabs_for(program, role=None):
    return [tab for tab in MODULE_TABS.get(program, []) if can(role, tab["permission"])]
