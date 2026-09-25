from datetime import datetime, timedelta


def require_utc(value: datetime) -> datetime:
    """Return value when it is timezone-aware UTC; otherwise raise ValueError."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    if value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use UTC")
    return value

