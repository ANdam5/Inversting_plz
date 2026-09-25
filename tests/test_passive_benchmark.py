from decimal import Decimal

from investing_plz.backtest import run_backtest, run_passive_benchmark
from investing_plz.domain import OrderSide
from investing_plz.strategy import MovingAverageCrossoverStrategy
from tests.test_backtest import bars_from_closes, config


def test_full_btc_buy_and_hold_buys_once_and_marks_last_close() -> None:
    bars = bars_from_closes(["100", "150", "200"], opens={0: "100"})

    result = run_passive_benchmark(bars, config(), Decimal("1"))

    assert len(result.fills) == 1
    assert result.fills[0].side is OrderSide.BUY
    assert result.fills[0].timestamp == bars[0].timestamp
    assert result.fills[0].quantity == Decimal("10")
    assert result.final_cash == Decimal("0")
    assert result.final_position_quantity == Decimal("10")
    assert result.final_position_market_value == Decimal("2000")
    assert result.final_portfolio_value == Decimal("2000")


def test_ten_percent_passive_hold_keeps_cash_and_does_not_rebalance() -> None:
    bars = bars_from_closes(["100", "150", "200"], opens={0: "100"})

    result = run_passive_benchmark(bars, config(), Decimal("0.10"))

    assert len(result.fills) == 1
    assert result.fills[0].quantity == Decimal("1")
    assert result.final_cash == Decimal("900")
    assert result.final_position_quantity == Decimal("1")
    assert result.final_portfolio_value == Decimal("1100")


def test_passive_value_decreases_when_price_falls() -> None:
    bars = bars_from_closes(["100", "75", "50"], opens={0: "100"})

    result = run_passive_benchmark(bars, config(), Decimal("0.10"))

    assert result.final_portfolio_value == Decimal("950")
    assert result.total_return == Decimal("-0.05")


def test_initial_buy_applies_fee_slippage_step_and_never_overspends() -> None:
    bars = bars_from_closes(["100", "110", "120"], opens={0: "100"})

    result = run_passive_benchmark(
        bars,
        config(fee_rate=Decimal("0.01"), slippage_bps=Decimal("100")),
        Decimal("1"),
    )

    fill = result.fills[0]
    assert fill.fill_price == Decimal("101.00")
    assert fill.quantity == Decimal("9")
    assert fill.fee_amount == Decimal("9.0900")
    assert result.final_cash == Decimal("81.9100")
    assert result.final_cash >= 0


def test_passive_equity_curve_and_metrics_reuse_close_valuations() -> None:
    bars = bars_from_closes(["100", "120", "90", "110"], opens={0: "100"})

    result = run_passive_benchmark(bars, config(), Decimal("1"))

    assert len(result.equity_curve) == len(bars)
    assert [point.timestamp for point in result.equity_curve] == [
        bar.timestamp for bar in bars
    ]
    assert result.equity_curve[-1].portfolio_value == result.final_portfolio_value
    assert result.total_return == Decimal("0.1")
    assert result.maximum_drawdown == Decimal("-0.25")
    assert isinstance(result.cagr, Decimal)


def test_running_benchmarks_does_not_change_ma_backtest_result() -> None:
    bars = bars_from_closes(
        ["3", "2", "1", "4", "0", "0", "1"],
        opens={4: "100", 6: "80"},
    )
    strategy = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)
    backtest_config = config(fee_rate=Decimal("0.001"), slippage_bps=Decimal("5"))
    before = run_backtest(bars, strategy, backtest_config)

    run_passive_benchmark(bars, backtest_config, Decimal("0.10"))
    run_passive_benchmark(bars, backtest_config, Decimal("1"))
    after = run_backtest(bars, strategy, backtest_config)

    assert after == before
    assert after.fills == before.fills
    assert after.final_portfolio_value == before.final_portfolio_value
