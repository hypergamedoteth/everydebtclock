"""Calendar dates for builds and fetches.

GitHub Actions runs in UTC. After 6 PM Central (midnight UTC during standard
time) a UTC date is already the next day. As-of and built dates use Chicago.
"""
import datetime as dt
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")


def chicago_now(when=None):
    """Timezone-aware Chicago time. `when` may be a Unix timestamp."""
    if when is None:
        return dt.datetime.now(CT)
    if isinstance(when, (int, float)):
        return dt.datetime.fromtimestamp(when, CT)
    if when.tzinfo is None:
        return when.replace(tzinfo=CT)
    return when.astimezone(CT)


def chicago_today(when=None):
    return chicago_now(when).date()
