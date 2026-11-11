"""Per-user UI preferences stored in Supabase (`apex_user_settings`)."""
import logging
from datetime import datetime, timezone

from .config import Config
from .supabase import SupabaseError, eq, supabase

log = logging.getLogger(__name__)

ACCENTS = ["blue", "violet", "green", "orange", "pink", "grey"]
MODES = ["light", "dark"]
ORIENTATIONS = ["landscape", "portrait"]
DEFAULTS = {"electric_border": True, "accent": "blue", "mode": "dark", "orientation": "landscape"}


def clean(values, base=None):
    """Merge and validate user-supplied preferences on top of `base`."""
    prefs = dict(base or DEFAULTS)
    if "electric_border" in values:
        raw = values["electric_border"]
        prefs["electric_border"] = raw is True or str(raw).lower() in ("1", "true", "on", "yes")
    for key, allowed in (("accent", ACCENTS), ("mode", MODES), ("orientation", ORIENTATIONS)):
        if values.get(key) in allowed:
            prefs[key] = values[key]
    return prefs


def load(domain):
    try:
        rows = supabase.select(Config.SETTINGS_TABLE, {"domain": eq(domain)}, limit=1)
    except SupabaseError as exc:
        log.warning("Preferences unavailable: %s", exc)
        return dict(DEFAULTS)
    return clean(rows[0]) if rows else dict(DEFAULTS)


def save(domain, prefs):
    row = {"domain": domain, **prefs, "updated_at": datetime.now(timezone.utc).isoformat()}
    supabase.insert(Config.SETTINGS_TABLE, row, on_conflict="domain")
    return prefs
