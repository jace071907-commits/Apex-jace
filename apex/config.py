"""Central configuration. Every value is read from environment variables."""
import os
from datetime import timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT_DIR / ".env")
except ImportError:
    pass


def _env(key, default=""):
    value = os.environ.get(key)
    return default if value is None or value.strip() == "" else value.strip()


class Config:
    IS_PRODUCTION = bool(os.environ.get("VERCEL")) or _env("APEX_ENV") == "production"

    SUPABASE_URL = _env("SUPABASE_URL").rstrip("/")
    SUPABASE_PUBLISHABLE_KEY = _env("SUPABASE_PUBLISHABLE_KEY")
    SUPABASE_SECRET_KEY = _env("SUPABASE_SECRET_KEY")

    SECRET_KEY = _env("APEX_SECRET_KEY")
    SESSION_IDLE = timedelta(minutes=int(_env("APEX_SESSION_IDLE_MINUTES", "30")))
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(_env("APEX_SESSION_MAX_HOURS", "10")))
    SESSION_COOKIE_NAME = "apex_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = IS_PRODUCTION

    USER_TABLE = _env("APEX_USER_TABLE", "User")
    COL_DOMAIN = _env("APEX_COL_DOMAIN", "DOMAIN")
    COL_PASSWORD = _env("APEX_COL_PASSWORD", "PASSWORD")
    COL_ROLE = _env("APEX_COL_ROLE", "ROLE")
    COL_EMAIL = _env("APEX_COL_EMAIL", "EMAIL ADDRESS")
    AUTH_EMAIL_DOMAIN = _env("APEX_AUTH_EMAIL_DOMAIN", "apex.carelon.local")

    # Business timezone for "current date" (must match public.apex_today() in the SQL migration)
    TIMEZONE = _env("APEX_TIMEZONE", "Asia/Manila")

    # Disputes and Intakes module tables
    PEND_TABLE = _env("APEX_PEND_TABLE", "Pend")
    PEND_ID_COL = _env("APEX_PEND_ID_COL", "id")
    HISTORY_TABLE = _env("APEX_HISTORY_TABLE", "apex_pend_history")
    NOTIFICATION_TABLE = _env("APEX_NOTIFICATION_TABLE", "apex_notification")
    SETTINGS_TABLE = _env("APEX_SETTINGS_TABLE", "apex_user_settings")

    @classmethod
    def missing(cls):
        required = {
            "SUPABASE_URL": cls.SUPABASE_URL,
            "SUPABASE_PUBLISHABLE_KEY": cls.SUPABASE_PUBLISHABLE_KEY,
            "SUPABASE_SECRET_KEY": cls.SUPABASE_SECRET_KEY,
            "APEX_SECRET_KEY": cls.SECRET_KEY,
        }
        return [k for k, v in required.items() if not v]
