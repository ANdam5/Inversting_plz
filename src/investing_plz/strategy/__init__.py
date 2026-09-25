"""Provider-independent trading strategy rules."""

from investing_plz.strategy.moving_average_crossover import (
    InsufficientDataError,
    MovingAverageCrossoverEvaluation,
    MovingAverageCrossoverStrategy,
)
from investing_plz.strategy.protocol import Strategy
from investing_plz.strategy.signal import Signal, SignalType

__all__ = [
    "InsufficientDataError",
    "MovingAverageCrossoverEvaluation",
    "MovingAverageCrossoverStrategy",
    "Signal",
    "SignalType",
    "Strategy",
]

