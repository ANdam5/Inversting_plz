import pytest

from investing_plz.domain import Instrument
from investing_plz.strategy import (
    MovingAverageCrossoverParameters,
    MovingAverageCrossoverStrategy,
    MovingAverageParameterOverrides,
    StrategyProfile,
    create_strategy_from_profile,
    resolve_moving_average_parameters,
)


def make_profile(symbol: str, fast: int, slow: int) -> StrategyProfile:
    return StrategyProfile(
        instrument=Instrument(venue="upbit", symbol=symbol),
        strategy_id="moving_average_crossover",
        parameters=MovingAverageCrossoverParameters(
            fast_window=fast,
            slow_window=slow,
        ),
    )


def test_btc_and_eth_profiles_use_same_strategy_with_different_parameters() -> None:
    btc_profile = make_profile("KRW-BTC", fast=20, slow=60)
    eth_profile = make_profile("KRW-ETH", fast=15, slow=50)

    btc_strategy = create_strategy_from_profile(btc_profile)
    eth_strategy = create_strategy_from_profile(eth_profile)

    assert type(btc_strategy) is MovingAverageCrossoverStrategy
    assert type(eth_strategy) is MovingAverageCrossoverStrategy
    assert (btc_strategy.fast_window, btc_strategy.slow_window) == (20, 60)
    assert (eth_strategy.fast_window, eth_strategy.slow_window) == (15, 50)
    assert btc_profile.instrument.symbol == "KRW-BTC"
    assert eth_profile.instrument.symbol == "KRW-ETH"


@pytest.mark.parametrize(
    ("fast", "slow", "message"),
    [
        (0, 60, "fast_window"),
        (-1, 60, "fast_window"),
        (20, 0, "slow_window"),
        (20, -1, "slow_window"),
        (20, 20, "smaller"),
        (60, 20, "smaller"),
    ],
)
def test_profile_parameters_reject_invalid_windows(
    fast: int, slow: int, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        make_profile("KRW-BTC", fast=fast, slow=slow)


def test_profile_rejects_unknown_strategy_without_a_registry() -> None:
    with pytest.raises(ValueError, match="unsupported strategy_id"):
        StrategyProfile(
            instrument=Instrument("upbit", "KRW-BTC"),
            strategy_id="not_implemented",
            parameters=MovingAverageCrossoverParameters(20, 60),
        )


def test_parameter_resolution_uses_defaults_without_profile_or_overrides() -> None:
    defaults = MovingAverageCrossoverParameters(20, 60)

    assert resolve_moving_average_parameters(defaults) == defaults


def test_profile_parameters_override_defaults() -> None:
    defaults = MovingAverageCrossoverParameters(20, 60)
    profile = make_profile("KRW-ETH", fast=15, slow=50)

    resolved = resolve_moving_average_parameters(defaults, profile=profile)

    assert resolved == MovingAverageCrossoverParameters(15, 50)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (MovingAverageParameterOverrides(fast_window=10), (10, 50)),
        (MovingAverageParameterOverrides(slow_window=80), (15, 80)),
        (MovingAverageParameterOverrides(fast_window=10, slow_window=30), (10, 30)),
    ],
)
def test_runtime_partial_overrides_take_priority_over_profile(
    overrides: MovingAverageParameterOverrides,
    expected: tuple[int, int],
) -> None:
    profile = make_profile("KRW-ETH", fast=15, slow=50)

    resolved = resolve_moving_average_parameters(
        MovingAverageCrossoverParameters(20, 60),
        profile=profile,
        runtime_overrides=overrides,
    )

    assert (resolved.fast_window, resolved.slow_window) == expected


def test_btc_and_eth_use_the_same_parameter_resolution_logic() -> None:
    defaults = MovingAverageCrossoverParameters(20, 60)
    runtime_overrides = MovingAverageParameterOverrides(slow_window=80)

    btc = resolve_moving_average_parameters(
        defaults,
        profile=make_profile("KRW-BTC", fast=20, slow=60),
        runtime_overrides=runtime_overrides,
    )
    eth = resolve_moving_average_parameters(
        defaults,
        profile=make_profile("KRW-ETH", fast=15, slow=50),
        runtime_overrides=runtime_overrides,
    )

    assert btc == MovingAverageCrossoverParameters(20, 80)
    assert eth == MovingAverageCrossoverParameters(15, 80)


@pytest.mark.parametrize(
    "overrides",
    [
        MovingAverageParameterOverrides(fast_window=60),
        MovingAverageParameterOverrides(fast_window=0),
        MovingAverageParameterOverrides(fast_window=-1),
        MovingAverageParameterOverrides(slow_window=0),
        MovingAverageParameterOverrides(slow_window=-1),
    ],
)
def test_parameter_resolution_reuses_final_parameter_validation(
    overrides: MovingAverageParameterOverrides,
) -> None:
    with pytest.raises(ValueError):
        resolve_moving_average_parameters(
            MovingAverageCrossoverParameters(20, 50),
            profile=make_profile("KRW-ETH", fast=15, slow=50),
            runtime_overrides=overrides,
        )


def test_profile_strategy_creation_accepts_runtime_override() -> None:
    strategy = create_strategy_from_profile(
        make_profile("KRW-ETH", fast=15, slow=50),
        runtime_overrides=MovingAverageParameterOverrides(slow_window=80),
    )

    assert (strategy.fast_window, strategy.slow_window) == (15, 80)
