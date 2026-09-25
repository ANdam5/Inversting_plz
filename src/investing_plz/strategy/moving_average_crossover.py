from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from investing_plz.domain import Bar
from investing_plz.indicators import simple_moving_average
from investing_plz.strategy.signal import Signal, SignalType


class InsufficientDataError(ValueError):
    """There are not enough bars to evaluate the strategy."""


@dataclass(frozen=True, slots=True)
class MovingAverageCrossoverEvaluation:
    signal: Signal
    previous_fast_ma: Decimal
    previous_slow_ma: Decimal
    current_fast_ma: Decimal
    current_slow_ma: Decimal


class MovingAverageCrossoverStrategy:
    strategy_id = "moving_average_crossover"

    def __init__(self, *, fast_window: int = 20, slow_window: int = 60) -> None:
        if fast_window <= 0 or slow_window <= 0:
            raise ValueError("moving average windows must be greater than zero")
        if fast_window >= slow_window:
            raise ValueError("fast_window must be smaller than slow_window")
        self.fast_window = fast_window
        self.slow_window = slow_window

    @property
    def minimum_bars(self) -> int:
        return self.slow_window + 1

    def generate_signal(self, bars: Sequence[Bar]) -> Signal:
        return self.evaluate(bars).signal

    def evaluate(self, bars: Sequence[Bar]) -> MovingAverageCrossoverEvaluation:
        if len(bars) < self.minimum_bars:
            raise InsufficientDataError(
                f"strategy requires at least {self.minimum_bars} closed bars; "
                f"received {len(bars)}"
            )
        _validate_bars(bars)

        closes = [bar.close for bar in bars]
        previous = closes[:-1]
        previous_fast = simple_moving_average(previous, self.fast_window)
        previous_slow = simple_moving_average(previous, self.slow_window)
        current_fast = simple_moving_average(closes, self.fast_window)
        current_slow = simple_moving_average(closes, self.slow_window)
        assert previous_fast is not None
        assert previous_slow is not None
        assert current_fast is not None
        assert current_slow is not None

        if previous_fast <= previous_slow and current_fast > current_slow:
            signal_type = SignalType.BULLISH_CROSSOVER
        elif previous_fast >= previous_slow and current_fast < current_slow:
            signal_type = SignalType.BEARISH_CROSSOVER
        else:
            signal_type = SignalType.NEUTRAL

        latest = bars[-1]
        return MovingAverageCrossoverEvaluation(
            signal=Signal(
                instrument=latest.instrument,
                timestamp=latest.timestamp,
                signal_type=signal_type,
                strategy_id=self.strategy_id,
            ),
            previous_fast_ma=previous_fast,
            previous_slow_ma=previous_slow,
            current_fast_ma=current_fast,
            current_slow_ma=current_slow,
        )


def _validate_bars(bars: Sequence[Bar]) -> None:
    instrument = bars[0].instrument
    if any(bar.instrument != instrument for bar in bars):
        raise ValueError("all bars must belong to the same instrument")
    timestamps = [bar.timestamp for bar in bars]
    if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
        raise ValueError("bars must have unique timestamps in ascending order")

