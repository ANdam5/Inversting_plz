from datetime import datetime, timedelta, timezone

import pytest

from investing_plz.clock import Clock, FixedClock, SystemClock


def test_fixed_clock_returns_the_same_utc_time() -> None:
    current = datetime(2026, 9, 26, 3, 4, tzinfo=timezone.utc)
    clock: Clock = FixedClock(current)

    assert clock.now() == current
    assert clock.now() == current


def test_fixed_clock_rejects_naive_and_non_utc_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FixedClock(datetime(2026, 9, 26))
    with pytest.raises(ValueError, match="UTC"):
        FixedClock(datetime(2026, 9, 26, tzinfo=timezone(timedelta(hours=9))))


def test_system_clock_returns_timezone_aware_utc() -> None:
    current = SystemClock().now()

    assert current.tzinfo is not None
    assert current.utcoffset() == timedelta(0)
