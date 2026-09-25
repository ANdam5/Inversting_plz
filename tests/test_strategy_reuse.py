from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from investing_plz.domain import Bar, Instrument
from investing_plz.strategy import MovingAverageCrossoverStrategy, SignalType


def bars_for(instrument: Instrument, closes: list[int]) -> list[Bar]:
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


@pytest.mark.parametrize("symbol", ["KRW-BTC", "KRW-ETH"])
def test_same_strategy_class_works_for_different_instruments(symbol: str) -> None:
    instrument = Instrument(venue="upbit", symbol=symbol)
    strategy = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)

    signal = strategy.generate_signal(bars_for(instrument, [3, 2, 1, 4]))

    assert signal.signal_type is SignalType.BULLISH_CROSSOVER
    assert signal.instrument == instrument
    assert signal.strategy_id == "moving_average_crossover"


def test_same_strategy_class_accepts_different_parameter_sets() -> None:
    instrument = Instrument(venue="upbit", symbol="KRW-BTC")
    bars = bars_for(instrument, [1, 1, 2, 1, 1])
    short_parameters = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)
    long_parameters = MovingAverageCrossoverStrategy(fast_window=3, slow_window=4)

    short_signal = short_parameters.generate_signal(bars)
    long_signal = long_parameters.generate_signal(bars)

    assert type(short_parameters) is type(long_parameters)
    assert short_signal.signal_type is SignalType.BEARISH_CROSSOVER
    assert long_signal.signal_type is SignalType.NEUTRAL

