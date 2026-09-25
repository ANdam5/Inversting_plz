from datetime import datetime, timedelta

from investing_plz.domain import Bar
from investing_plz.domain.time import require_utc


def is_closed_bar(bar: Bar, *, now: datetime) -> bool:
    """Return whether a 24/7 daily bar has reached the end of its interval."""

    return is_closed_timestamp(bar.timestamp, bar.interval, now=now)


def is_closed_timestamp(
    timestamp: datetime, interval: str, *, now: datetime
) -> bool:
    require_utc(now)
    require_utc(timestamp)
    if interval != "day":
        raise ValueError("closed candle checks currently support only day bars")
    return now >= timestamp + timedelta(days=1)
