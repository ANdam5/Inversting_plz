import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from investing_plz.backtest import (
    BacktestConfig,
    BacktestRunMetadata,
    create_backtest_run_metadata,
    run_backtest,
)
from investing_plz.domain import Bar, Instrument
from investing_plz.risk import RiskLimits
from investing_plz.strategy import MovingAverageCrossoverStrategy


BTC = Instrument("upbit", "KRW-BTC")
START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def make_bars(instrument: Instrument = BTC) -> tuple[Bar, ...]:
    bars = []
    for index, close in enumerate(("3", "2", "1", "4", "5")):
        value = Decimal(close)
        bars.append(
            Bar(
                instrument=instrument,
                interval="day",
                timestamp=START + timedelta(days=index),
                open=value,
                high=value,
                low=value,
                close=value,
                volume=Decimal("1"),
            )
        )
    return tuple(bars)


def config() -> BacktestConfig:
    return BacktestConfig(
        initial_cash=Decimal("10000000"),
        target_weight=Decimal("0.10"),
        quantity_step=Decimal("0.00000001"),
        min_trade_amount=Decimal("10000"),
        fee_rate=Decimal("0.0005"),
        slippage_bps=Decimal("5"),
        risk_limits=RiskLimits(
            max_order_amount=Decimal("500000"),
            max_instrument_weight=Decimal("0.20"),
            min_cash_reserve=Decimal("1000000"),
        ),
    )


def make_metadata(instrument: Instrument = BTC) -> BacktestRunMetadata:
    return create_backtest_run_metadata(
        make_bars(instrument),
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(),
        code_version="M3-C1",
        dataset_version="fixture-v1",
    )


def test_metadata_records_dataset_strategy_risk_and_cost_configuration() -> None:
    metadata = make_metadata()

    assert metadata.instrument == BTC
    assert metadata.timeframe == "day"
    assert metadata.dataset_start == START
    assert metadata.dataset_end == START + timedelta(days=4)
    assert metadata.bar_count == 5
    assert metadata.dataset_version == "fixture-v1"
    assert (metadata.fast_window, metadata.slow_window) == (2, 3)
    assert metadata.max_order_amount == Decimal("500000")
    assert metadata.max_instrument_weight == Decimal("0.20")
    assert metadata.min_cash_reserve == Decimal("1000000")
    assert metadata.fee_rate == Decimal("0.0005")
    assert metadata.slippage_bps == Decimal("5")
    assert metadata.code_version == "M3-C1"


def test_metadata_json_round_trip_preserves_decimal_and_utc_values() -> None:
    original = make_metadata()
    payload = json.loads(json.dumps(original.to_dict()))

    assert payload["initial_cash"] == "10000000"
    assert payload["target_weight"] == "0.1"
    assert payload["dataset_start"] == "2024-01-01T00:00:00+00:00"
    assert BacktestRunMetadata.from_dict(payload) == original


def test_metadata_supports_different_instruments() -> None:
    eth = make_metadata(Instrument("upbit", "KRW-ETH"))

    assert eth.instrument == Instrument("upbit", "KRW-ETH")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"dataset_end": START - timedelta(days=1)}, "dataset_start"),
        ({"bar_count": 0}, "bar_count"),
        ({"fast_window": 3, "slow_window": 3}, "smaller"),
        ({"fast_window": 0}, "fast_window"),
        ({"initial_cash": Decimal("0")}, "initial_cash"),
        ({"target_weight": Decimal("1.1")}, "target_weight"),
        ({"quantity_step": Decimal("0")}, "quantity_step"),
        ({"min_trade_amount": Decimal("-1")}, "min_trade_amount"),
        ({"max_order_amount": Decimal("0")}, "max_order_amount"),
        ({"max_instrument_weight": Decimal("0")}, "max_instrument_weight"),
        ({"min_cash_reserve": Decimal("-1")}, "min_cash_reserve"),
        ({"fee_rate": Decimal("1")}, "fee_rate"),
        ({"slippage_bps": Decimal("10000")}, "slippage_bps"),
        ({"code_version": ""}, "code_version"),
        ({"dataset_version": ""}, "dataset_version"),
    ],
)
def test_metadata_rejects_invalid_values(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        replace(make_metadata(), **changes)


def test_identical_inputs_create_identical_metadata() -> None:
    assert make_metadata() == make_metadata()


def test_runner_attaches_metadata_without_changing_results() -> None:
    bars = make_bars()
    strategy = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)
    baseline = run_backtest(bars, strategy, config())
    recorded = run_backtest(
        bars,
        strategy,
        config(),
        code_version="M3-C1",
        dataset_version="fixture-v1",
    )

    assert baseline.metadata is None
    assert recorded.metadata == make_metadata()
    assert replace(recorded, metadata=None) == baseline


def test_runner_requires_both_explicit_versions() -> None:
    with pytest.raises(ValueError, match="provided together"):
        run_backtest(
            make_bars(),
            MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
            config(),
            code_version="M3-C1",
        )
