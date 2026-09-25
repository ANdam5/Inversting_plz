import pytest

from investing_plz.domain import Instrument
from investing_plz.strategy import (
    MovingAverageCrossoverParameters,
    MovingAverageCrossoverStrategy,
    StrategyProfile,
    create_strategy_from_profile,
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
