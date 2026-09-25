from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from investing_plz.domain import Bar, Instrument
from investing_plz.market_data import MarketDataValidationError
from investing_plz.market_data.validation import validate_bar_series


def make_bar(day: int) -> Bar:
    return Bar(
        instrument=Instrument("upbit", "KRW-BTC"),
        interval="day",
        timestamp=datetime(2026, 9, day, tzinfo=timezone.utc),
        open=Decimal("100"), high=Decimal("120"), low=Decimal("90"),
        close=Decimal("110"), volume=Decimal("1"),
    )


def test_rejects_duplicate_timestamps() -> None:
    bar = make_bar(23)
    with pytest.raises(MarketDataValidationError, match="duplicate"):
        validate_bar_series([bar, bar], "day")


def test_rejects_reversed_normalized_bars() -> None:
    with pytest.raises(MarketDataValidationError, match="ascending"):
        validate_bar_series([make_bar(24), make_bar(23)], "day")


def test_detects_gap_between_daily_candles() -> None:
    with pytest.raises(MarketDataValidationError, match="missing candle"):
        validate_bar_series([make_bar(22), make_bar(24)], "day")


def test_detects_gap_from_previously_stored_candle() -> None:
    with pytest.raises(MarketDataValidationError, match="missing candle"):
        validate_bar_series(
            [make_bar(24)],
            "day",
            previous_timestamp=make_bar(22).timestamp,
        )


def test_does_not_require_a_candle_after_latest_returned_bar() -> None:
    current_incomplete = make_bar(24)
    validate_bar_series(
        [current_incomplete],
        "day",
        previous_timestamp=current_incomplete.timestamp - timedelta(days=1),
    )
