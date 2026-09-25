from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from investing_plz.domain import Bar, Instrument
from investing_plz.strategy import (
    InsufficientDataError,
    MovingAverageCrossoverStrategy,
    SignalType,
    Strategy,
)


def bars_from_closes(closes: list[int]) -> list[Bar]:
    instrument = Instrument("upbit", "KRW-BTC")
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Bar(
            instrument=instrument,
            interval="day",
            timestamp=start + timedelta(days=index),
            open=Decimal(close),
            high=Decimal(close),
            low=Decimal(close),
            close=Decimal(close),
            volume=Decimal("1"),
        )
        for index, close in enumerate(closes)
    ]


@pytest.mark.parametrize(
    ("closes", "expected"),
    [
        ([3, 2, 1, 4], SignalType.BULLISH_CROSSOVER),
        ([1, 2, 3, 0], SignalType.BEARISH_CROSSOVER),
        ([1, 3, 4, 5], SignalType.NEUTRAL),
        ([5, 3, 2, 1], SignalType.NEUTRAL),
    ],
)
def test_crossover_signal_uses_previous_and_current_averages(
    closes: list[int], expected: SignalType
) -> None:
    strategy: Strategy = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)

    signal = strategy.generate_signal(bars_from_closes(closes))

    assert signal.signal_type is expected
    assert signal.strategy_id == "moving_average_crossover"


def test_strategy_requires_slow_window_plus_one_bars() -> None:
    strategy = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)

    assert strategy.minimum_bars == 4
    with pytest.raises(InsufficientDataError, match="at least 4 closed bars"):
        strategy.generate_signal(bars_from_closes([1, 2, 3]))


@pytest.mark.parametrize(
    ("fast", "slow"),
    [(0, 3), (2, 0), (3, 3), (4, 3)],
)
def test_strategy_rejects_invalid_windows(fast: int, slow: int) -> None:
    with pytest.raises(ValueError):
        MovingAverageCrossoverStrategy(fast_window=fast, slow_window=slow)

