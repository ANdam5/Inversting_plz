from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from investing_plz.domain import Bar, Instrument
from investing_plz.market_data import is_closed_bar


def make_bar(timestamp: datetime) -> Bar:
    return Bar(
        instrument=Instrument("upbit", "KRW-BTC"),
        interval="day",
        timestamp=timestamp,
        open=Decimal("100"),
        high=Decimal("120"),
        low=Decimal("90"),
        close=Decimal("110"),
        volume=Decimal("1"),
    )


def test_past_daily_bar_is_closed() -> None:
    bar = make_bar(datetime(2026, 9, 23, tzinfo=timezone.utc))
    now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)

    assert is_closed_bar(bar, now=now)


def test_current_daily_bar_is_not_closed() -> None:
    bar = make_bar(datetime(2026, 9, 25, tzinfo=timezone.utc))
    now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)

    assert not is_closed_bar(bar, now=now)


def test_bar_closes_exactly_at_next_utc_boundary() -> None:
    bar = make_bar(datetime(2026, 9, 24, tzinfo=timezone.utc))

    assert not is_closed_bar(
        bar,
        now=datetime(2026, 9, 25, tzinfo=timezone.utc) - timedelta(microseconds=1),
    )
    assert is_closed_bar(bar, now=datetime(2026, 9, 25, tzinfo=timezone.utc))


def test_fixed_now_is_deterministic() -> None:
    bar = make_bar(datetime(2026, 9, 25, tzinfo=timezone.utc))
    now = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)

    assert [is_closed_bar(bar, now=now) for _ in range(3)] == [False] * 3


def test_naive_now_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        is_closed_bar(
            make_bar(datetime(2026, 9, 24, tzinfo=timezone.utc)),
            now=datetime(2026, 9, 25),
        )
