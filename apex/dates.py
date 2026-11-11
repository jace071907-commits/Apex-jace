"""Business-date helpers (timezone-aware "current date")."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .config import Config

_TZ = ZoneInfo(Config.TIMEZONE)


def today():
    return datetime.now(_TZ).date()


def parse(value):
    """Parse an ISO date/timestamp (or date object) into a date; None when empty/invalid."""
    if isinstance(value, date):
        return value if not isinstance(value, datetime) else value.date()
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def days_since(value):
    d = parse(value)
    return max((today() - d).days, 0) if d else None


def display(value):
    d = parse(value)
    return d.strftime("%b %d, %Y") if d else ""


def display_datetime(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(_TZ)
    except (TypeError, ValueError):
        return display(value)
    return dt.strftime("%b %d, %Y · %I:%M %p")
