"""Provider-independent trading strategy rules."""

from investing_plz.strategy.moving_average_crossover import (
    InsufficientDataError,
    MovingAverageCrossoverEvaluation,
    MovingAverageCrossoverStrategy,
)
from investing_plz.strategy.protocol import Strategy
from investing_plz.strategy.profile import (
    MovingAverageCrossoverParameters,
    MovingAverageParameterOverrides,
    StrategyProfile,
    create_strategy_from_profile,
    resolve_moving_average_parameters,
)
from investing_plz.strategy.signal import Signal, SignalType

__all__ = [
    "InsufficientDataError",
    "MovingAverageCrossoverEvaluation",
    "MovingAverageCrossoverStrategy",
    "MovingAverageCrossoverParameters",
    "MovingAverageParameterOverrides",
    "Signal",
    "SignalType",
    "Strategy",
    "StrategyProfile",
    "create_strategy_from_profile",
    "resolve_moving_average_parameters",
]
