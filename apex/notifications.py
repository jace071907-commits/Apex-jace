"""User notifications. Rows are created by the `apex_pend_after` database trigger."""
import logging

from . import dates
from .config import Config
from .supabase import SupabaseError, eq, supabase

log = logging.getLogger(__name__)


def _shape(row):
    return {
        "id": row.get("id"),
        "kind": row.get("kind"),
        "title": row.get("title"),
        "message": row.get("message"),
        "inquiry_number": row.get("inquiry_number"),
        "is_read": bool(row.get("is_read")),
        "when": dates.display_datetime(row.get("created_at")),
    }


def inbox(domain, limit=10):
    """Return (unread_count, latest notifications). Degrades to empty if the table is unavailable."""
    try:
        unread = supabase.count(Config.NOTIFICATION_TABLE, {"domain": eq(domain), "is_read": "is.false"})
        rows = supabase.select(Config.NOTIFICATION_TABLE, {"domain": eq(domain), "order": "created_at.desc"},
                               limit=limit)
    except SupabaseError as exc:
        log.warning("Notifications unavailable: %s", exc)
        return 0, []
    return unread, [_shape(r) for r in rows]


def mark_read(domain, notification_id=None):
    params = {"domain": eq(domain), "is_read": "is.false"}
    if notification_id is not None:
        params["id"] = eq(int(notification_id))
    supabase.update(Config.NOTIFICATION_TABLE, params, {"is_read": True})
