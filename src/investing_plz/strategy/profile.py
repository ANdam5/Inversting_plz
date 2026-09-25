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
class MovingAverageParameterOverrides:
    fast_window: int | None = None
    slow_window: int | None = None


@dataclass(frozen=True, slots=True)
class StrategyProfile:
    instrument: Instrument
    strategy_id: str
    parameters: MovingAverageCrossoverParameters

    def __post_init__(self) -> None:
        if self.strategy_id != MovingAverageCrossoverStrategy.strategy_id:
            raise ValueError(f"unsupported strategy_id: {self.strategy_id}")


def resolve_moving_average_parameters(
    default_parameters: MovingAverageCrossoverParameters,
    *,
    profile: StrategyProfile | None = None,
    runtime_overrides: MovingAverageParameterOverrides | None = None,
) -> MovingAverageCrossoverParameters:
    base = profile.parameters if profile is not None else default_parameters
    overrides = runtime_overrides or MovingAverageParameterOverrides()
    return MovingAverageCrossoverParameters(
        fast_window=(
            overrides.fast_window
            if overrides.fast_window is not None
            else base.fast_window
        ),
        slow_window=(
            overrides.slow_window
            if overrides.slow_window is not None
            else base.slow_window
        ),
    )


def create_strategy_from_profile(
    profile: StrategyProfile,
    *,
    runtime_overrides: MovingAverageParameterOverrides | None = None,
) -> MovingAverageCrossoverStrategy:
    parameters = resolve_moving_average_parameters(
        profile.parameters,
        profile=profile,
        runtime_overrides=runtime_overrides,
    )
    return MovingAverageCrossoverStrategy(
        fast_window=parameters.fast_window,
        slow_window=parameters.slow_window,
    )
