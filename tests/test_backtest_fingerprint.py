import json
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from investing_plz.backtest import (
    BacktestConfig,
    BacktestRunMetadata,
    build_closed_trades,
    calculate_trade_metrics,
    canonical_metadata_json,
    run_backtest,
)
from investing_plz.domain import Bar, Instrument
from investing_plz.risk import RiskLimits
from investing_plz.strategy import MovingAverageCrossoverStrategy


START = datetime(2024, 1, 1, tzinfo=timezone.utc)
INSTRUMENT = Instrument("upbit", "KRW-BTC")


def bars() -> tuple[Bar, ...]:
    result = []
    for index, close in enumerate(("3", "2", "1", "4", "5", "6", "2", "1")):
        value = Decimal(close)
        result.append(
            Bar(
                instrument=INSTRUMENT,
                interval="day",
                timestamp=START + timedelta(days=index),
                open=value,
                high=value,
                low=value,
                close=value,
                volume=Decimal("1"),
            )
        )
    return tuple(result)


def config() -> BacktestConfig:
    return BacktestConfig(
        initial_cash=Decimal("1000"),
        target_weight=Decimal("0.5"),
        quantity_step=Decimal("0.01"),
        min_trade_amount=Decimal("1"),
        fee_rate=Decimal("0.001"),
        slippage_bps=Decimal("5"),
        risk_limits=RiskLimits(
            max_order_amount=Decimal("500"),
            max_instrument_weight=Decimal("0.8"),
            min_cash_reserve=Decimal("100"),
        ),
    )


def metadata() -> BacktestRunMetadata:
    result = run_backtest(
        bars(),
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(),
        code_version="M3-C1",
        dataset_version="fixture-v1",
    )
    assert result.metadata is not None
    return result.metadata


def test_identical_metadata_has_identical_sha256_fingerprint() -> None:
    first = metadata().fingerprint
    second = metadata().fingerprint

    assert first == second
    assert re.fullmatch(r"[0-9a-f]{64}", first)


def test_serialization_round_trip_keeps_fingerprint() -> None:
    original = metadata()
    restored = BacktestRunMetadata.from_dict(
        json.loads(json.dumps(original.to_dict()))
    )

    assert restored.fingerprint == original.fingerprint


def test_equivalent_decimal_target_weights_have_same_fingerprint() -> None:
    original = metadata()
    with_trailing_zero = replace(original, target_weight=Decimal("0.10"))
    without_trailing_zero = replace(original, target_weight=Decimal("0.1"))

    assert with_trailing_zero.to_dict()["target_weight"] == "0.1"
    assert without_trailing_zero.to_dict()["target_weight"] == "0.1"
    assert with_trailing_zero.fingerprint == without_trailing_zero.fingerprint


def test_equivalent_decimal_amounts_have_same_fingerprint() -> None:
    original = metadata()
    integer_scale = replace(original, max_order_amount=Decimal("500000"))
    fractional_scale = replace(original, max_order_amount=Decimal("500000.0"))

    assert integer_scale.to_dict()["max_order_amount"] == "500000"
    assert fractional_scale.to_dict()["max_order_amount"] == "500000"
    assert integer_scale.fingerprint == fractional_scale.fingerprint


def test_decimal_zero_representations_are_canonical() -> None:
    original = metadata()
    zero = replace(original, min_trade_amount=Decimal("0"))
    scaled_zero = replace(original, min_trade_amount=Decimal("0.00"))
    negative_zero = replace(original, min_trade_amount=Decimal("-0"))

    assert zero.to_dict()["min_trade_amount"] == "0"
    assert scaled_zero.to_dict()["min_trade_amount"] == "0"
    assert negative_zero.to_dict()["min_trade_amount"] == "0"
    assert len({zero.fingerprint, scaled_zero.fingerprint, negative_zero.fingerprint}) == 1


def test_different_decimal_values_have_different_fingerprints() -> None:
    original = metadata()

    assert replace(
        original, target_weight=Decimal("0.1")
    ).fingerprint != replace(
        original, target_weight=Decimal("0.11")
    ).fingerprint


def test_different_slow_windows_have_different_fingerprints() -> None:
    original = metadata()

    assert replace(original, slow_window=60).fingerprint != replace(
        original, slow_window=80
    ).fingerprint


def test_canonical_json_is_compact_and_key_sorted() -> None:
    canonical = canonical_metadata_json(metadata())

    assert " " not in canonical
    assert canonical == json.dumps(
        metadata().to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"instrument": Instrument("upbit", "KRW-ETH")},
        {"timeframe": "week"},
        {"dataset_version": "fixture-v2"},
        {"dataset_start": START + timedelta(hours=1)},
        {"dataset_end": START + timedelta(days=8)},
        {"bar_count": 9},
        {"fast_window": 1},
        {"slow_window": 4},
        {"initial_cash": Decimal("2000")},
        {"target_weight": Decimal("0.4")},
        {"max_order_amount": Decimal("400")},
        {"max_instrument_weight": Decimal("0.7")},
        {"min_cash_reserve": Decimal("50")},
        {"fee_rate": Decimal("0")},
        {"slippage_bps": Decimal("0")},
        {"code_version": "M3-C2"},
    ],
)
def test_any_metadata_condition_change_changes_fingerprint(
    changes: dict[str, object],
) -> None:
    original = metadata()
    changed = replace(original, **changes)

    assert changed.fingerprint != original.fingerprint


def test_result_without_metadata_has_no_fingerprint() -> None:
    result = run_backtest(
        bars(),
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(),
    )

    assert result.metadata is None
    assert result.run_fingerprint is None


def test_repeated_backtest_reproduces_fingerprint_and_all_results() -> None:
    strategy = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)
    first = run_backtest(
        bars(),
        strategy,
        config(),
        code_version="M3-C1",
        dataset_version="fixture-v1",
    )
    second = run_backtest(
        bars(),
        strategy,
        config(),
        code_version="M3-C1",
        dataset_version="fixture-v1",
    )

    assert first.metadata == second.metadata
    assert first.run_fingerprint == second.run_fingerprint
    assert first.fills == second.fills
    assert first.total_fees == second.total_fees
    assert first.final_cash == second.final_cash
    assert first.final_position_quantity == second.final_position_quantity
    assert first.final_portfolio_value == second.final_portfolio_value
    assert first.final_average_cost == second.final_average_cost
    assert first.cumulative_realized_pnl == second.cumulative_realized_pnl
    assert first.equity_curve == second.equity_curve
    assert first.total_return == second.total_return
    assert first.maximum_drawdown == second.maximum_drawdown
    assert first.cagr == second.cagr
    first_trades = build_closed_trades(first.fills)
    second_trades = build_closed_trades(second.fills)
    assert first.final_position_quantity == Decimal("0")
    assert len(first_trades) >= 1
    assert first_trades == second_trades
    assert sum(
        (trade.realized_pnl for trade in first_trades),
        start=Decimal("0"),
    ) == first.cumulative_realized_pnl
    assert calculate_trade_metrics(first_trades) == calculate_trade_metrics(
        second_trades
    )
