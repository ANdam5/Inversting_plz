from dataclasses import dataclass

from investing_plz.domain import Instrument
from investing_plz.strategy.moving_average_crossover import (
    MovingAverageCrossoverStrategy,
)


@dataclass(frozen=True, slots=True)
class MovingAverageCrossoverParameters:
    fast_window: int
    slow_window: int

    def __post_init__(self) -> None:
        if self.fast_window <= 0:
            raise ValueError("fast_window must be greater than zero")
        if self.slow_window <= 0:
            raise ValueError("slow_window must be greater than zero")
        if self.fast_window >= self.slow_window:
            raise ValueError("fast_window must be smaller than slow_window")


@dataclass(frozen=True, slots=True)
class StrategyProfile:
    instrument: Instrument
    strategy_id: str
    parameters: MovingAverageCrossoverParameters

    def __post_init__(self) -> None:
        if self.strategy_id != MovingAverageCrossoverStrategy.strategy_id:
            raise ValueError(f"unsupported strategy_id: {self.strategy_id}")


def create_strategy_from_profile(
    profile: StrategyProfile,
) -> MovingAverageCrossoverStrategy:
    return MovingAverageCrossoverStrategy(
        fast_window=profile.parameters.fast_window,
        slow_window=profile.parameters.slow_window,
    )

