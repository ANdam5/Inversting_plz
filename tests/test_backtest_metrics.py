from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from investing_plz.backtest import (
    EquityPoint,
    calculate_cagr,
    calculate_max_drawdown,
    calculate_total_return,
    run_backtest,
)
from investing_plz.strategy import MovingAverageCrossoverStrategy
from tests.test_backtest import bars_from_closes, config


ONE_YEAR = timedelta(days=365, hours=6)


def test_equity_curve_has_one_close_point_per_bar() -> None:
    bars = bars_from_closes(["3", "2", "1", "4", "5"], opens={4: "100"})

    result = run_backtest(
        bars,
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(),
    )

    assert len(result.equity_curve) == len(bars)
    assert [point.timestamp for point in result.equity_curve] == [
        bar.timestamp for bar in bars
    ]
    assert [point.portfolio_value for point in result.equity_curve[:4]] == [
        Decimal("1000")
    ] * 4
    assert result.equity_curve[4].portfolio_value == Decimal("525")
    assert result.equity_curve[-1].portfolio_value == result.final_portfolio_value


def test_cost_aware_equity_uses_fee_and_slippage_adjusted_portfolio() -> None:
    bars = bars_from_closes(["3", "2", "1", "4", "5"], opens={4: "100"})

    result = run_backtest(
        bars,
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(fee_rate=Decimal("0.01"), slippage_bps=Decimal("100")),
    )

    fill = result.fills[0]
    expected_cash = Decimal("1000") - fill.quantity * fill.fill_price - fill.fee_amount
    expected_equity = expected_cash + fill.quantity * bars[4].close
    assert result.equity_curve[4].portfolio_value == expected_equity
    assert expected_equity == Decimal("514.9500")


def test_equity_after_sell_matches_cash_plus_remaining_position_at_close() -> None:
    bars = bars_from_closes(
        ["3", "2", "1", "4", "0", "0", "1"],
        opens={4: "100", 6: "80"},
    )

    result = run_backtest(
        bars,
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(),
    )

    assert result.fills[-1].timestamp == bars[6].timestamp
    assert result.final_cash == Decimal("900")
    assert result.final_position_quantity == Decimal("0")
    assert result.equity_curve[6].portfolio_value == Decimal("900")


@pytest.mark.parametrize(
    ("initial", "final", "expected"),
    [
        ("100", "120", "0.20"),
        ("100", "80", "-0.20"),
    ],
)
def test_total_return(initial: str, final: str, expected: str) -> None:
    assert calculate_total_return(Decimal(initial), Decimal(final)) == Decimal(expected)


@pytest.mark.parametrize(
    ("years", "initial", "final", "expected"),
    [
        (1, "100", "110", "0.10"),
        (2, "100", "121", "0.10"),
        (2, "100", "81", "-0.10"),
        (3, "100", "100", "0"),
    ],
)
def test_cagr_for_profit_loss_and_no_change(
    years: int,
    initial: str,
    final: str,
    expected: str,
) -> None:
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    actual = calculate_cagr(
        Decimal(initial),
        Decimal(final),
        start,
        start + ONE_YEAR * years,
    )

    assert abs(actual - Decimal(expected)) < Decimal("1E-25")


def test_cagr_rejects_non_positive_initial_value_and_period() -> None:
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="initial_value"):
        calculate_cagr(Decimal("0"), Decimal("100"), start, start + ONE_YEAR)
    with pytest.raises(ValueError, match="period"):
        calculate_cagr(Decimal("100"), Decimal("110"), start, start)


def test_maximum_drawdown_uses_running_peak_and_is_negative() -> None:
    values = tuple(Decimal(value) for value in ("100", "120", "90", "110"))

    assert calculate_max_drawdown(values) == Decimal("-0.25")


def test_maximum_drawdown_uses_intermediate_peak() -> None:
    values = tuple(Decimal(value) for value in ("100", "150", "120", "140"))

    assert calculate_max_drawdown(values) == Decimal("-0.2")


def test_continuously_rising_equity_has_zero_drawdown() -> None:
    values = tuple(Decimal(value) for value in ("100", "110", "120"))

    assert calculate_max_drawdown(values) == Decimal("0")


def test_empty_equity_curve_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        calculate_max_drawdown(())


def test_equity_point_requires_utc_and_decimal() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        EquityPoint(datetime(2026, 1, 1), Decimal("100"))
    with pytest.raises(TypeError, match="Decimal"):
        EquityPoint(datetime(2026, 1, 1, tzinfo=timezone.utc), 100.0)


def test_result_metrics_and_equity_curve_are_deterministic() -> None:
    bars = bars_from_closes(
        ["3", "2", "1", "4", "0", "0", "1"],
        opens={4: "100", 6: "80"},
    )
    strategy = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)
    cost_config = config(fee_rate=Decimal("0.001"), slippage_bps=Decimal("5"))

    first = run_backtest(bars, strategy, cost_config)
    second = run_backtest(bars, strategy, cost_config)

    assert first == second
    assert first.equity_curve == second.equity_curve
    assert first.total_return == second.total_return
    assert first.maximum_drawdown == second.maximum_drawdown
    assert first.cagr == second.cagr


def test_cagr_observes_existing_result_without_changing_execution_outputs() -> None:
    bars = bars_from_closes(
        ["3", "2", "1", "4", "0", "0", "1"],
        opens={4: "100", 6: "80"},
    )
    result = run_backtest(
        bars,
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(fee_rate=Decimal("0.001"), slippage_bps=Decimal("5")),
    )
    execution_snapshot = (
        result.fills,
        result.final_portfolio_value,
        result.total_return,
        result.maximum_drawdown,
    )

    assert isinstance(result.cagr, Decimal)
    assert (
        result.fills,
        result.final_portfolio_value,
        result.total_return,
        result.maximum_drawdown,
    ) == execution_snapshot
