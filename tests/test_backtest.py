from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest

from investing_plz.backtest import (
    BacktestConfig,
    BacktestPortfolio,
    Fill,
    run_backtest,
)
from investing_plz.application.position_sizing import create_target_weight_order_intent
from investing_plz.domain import Bar, Instrument, OrderIntent, OrderSide
from investing_plz.risk import RiskLimits
from investing_plz.strategy import MovingAverageCrossoverStrategy


INSTRUMENT = Instrument("upbit", "KRW-BTC")


def bars_from_closes(
    closes: list[str], *, opens: dict[int, str] | None = None
) -> list[Bar]:
    opens = opens or {}
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    result = []
    for index, close_text in enumerate(closes):
        close = Decimal(close_text)
        open_price = Decimal(opens.get(index, close_text))
        result.append(
            Bar(
                instrument=INSTRUMENT,
                interval="day",
                timestamp=start + timedelta(days=index),
                open=open_price,
                high=max(open_price, close),
                low=min(open_price, close),
                close=close,
                volume=Decimal("1"),
            )
        )
    return result


def config(**overrides: object) -> BacktestConfig:
    values: dict[str, object] = {
        "initial_cash": Decimal("1000"),
        "target_weight": Decimal("0.5"),
        "quantity_step": Decimal("1"),
        "risk_limits": RiskLimits(
            max_order_amount=Decimal("10000"),
            max_instrument_weight=Decimal("1"),
            min_cash_reserve=Decimal("0"),
        ),
    }
    values.update(overrides)
    return BacktestConfig(**values)


def test_bullish_signal_fills_at_next_bar_open_not_signal_bar() -> None:
    bars = bars_from_closes(["3", "2", "1", "4", "5"], opens={4: "100"})

    result = run_backtest(bars, MovingAverageCrossoverStrategy(fast_window=2, slow_window=3), config())

    assert result.bullish_signal_count == 1
    assert result.fill_count == 1
    assert result.fills[0].timestamp == bars[4].timestamp
    assert result.fills[0].timestamp != bars[3].timestamp
    assert result.fills[0].fill_price == Decimal("100")
    assert result.fills[0].quantity == Decimal("5")


def test_bearish_signal_sells_at_the_following_open() -> None:
    bars = bars_from_closes(
        ["3", "2", "1", "4", "0", "0", "1"],
        opens={4: "100", 6: "80"},
    )

    result = run_backtest(bars, MovingAverageCrossoverStrategy(fast_window=2, slow_window=3), config())

    assert result.bearish_signal_count == 1
    assert [fill.side for fill in result.fills] == [OrderSide.BUY, OrderSide.SELL]
    assert result.fills[1].timestamp == bars[6].timestamp
    assert result.final_position_quantity == Decimal("0")
    assert result.final_cash == Decimal("900")


def test_neutral_signals_do_not_create_intents() -> None:
    result = run_backtest(
        bars_from_closes(["1", "2", "3", "4", "5"]),
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(),
    )

    assert result.signal_count == 2
    assert result.bullish_signal_count == 0
    assert result.bearish_signal_count == 0
    assert result.intent_count == 0


def test_signal_on_last_bar_has_no_fill() -> None:
    result = run_backtest(
        bars_from_closes(["3", "2", "1", "4"]),
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(),
    )

    assert result.bullish_signal_count == 1
    assert result.intent_count == 0
    assert result.fill_count == 0


def test_risk_approved_fills_original_quantity() -> None:
    result = run_backtest(
        bars_from_closes(["3", "2", "1", "4", "5"], opens={4: "100"}),
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(),
    )

    assert result.approved_count == 1
    assert result.adjusted_count == 0
    assert result.fills[0].quantity == Decimal("5")
    assert result.final_cash == Decimal("500")


def test_risk_adjusted_fills_reduced_quantity() -> None:
    result = run_backtest(
        bars_from_closes(["3", "2", "1", "4", "5"], opens={4: "100"}),
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(
            risk_limits=RiskLimits(
                max_order_amount=Decimal("200"),
                max_instrument_weight=Decimal("1"),
                min_cash_reserve=Decimal("0"),
            )
        ),
    )

    assert result.adjusted_count == 1
    assert result.fills[0].quantity == Decimal("2")


def test_adjusted_rebalance_continues_once_then_stops_after_approval() -> None:
    bars = bars_from_closes(
        ["3", "2", "1", "4", "5", "6", "7"],
        opens={4: "100", 5: "100", 6: "200"},
    )
    result = run_backtest(
        bars,
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(
            risk_limits=RiskLimits(
                max_order_amount=Decimal("300"),
                max_instrument_weight=Decimal("1"),
                min_cash_reserve=Decimal("0"),
            )
        ),
    )

    assert result.adjusted_count == 1
    assert result.approved_count == 1
    assert [fill.quantity for fill in result.fills] == [Decimal("3"), Decimal("2")]
    assert [fill.timestamp for fill in result.fills] == [bars[4].timestamp, bars[5].timestamp]
    assert result.fill_count == 2
    assert result.intent_count == 2


def test_rejected_rebalance_is_not_retried_on_neutral_bars() -> None:
    result = run_backtest(
        bars_from_closes(["3", "2", "1", "4", "5", "6", "7"]),
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(
            risk_limits=RiskLimits(
                max_order_amount=Decimal("10000"),
                max_instrument_weight=Decimal("1"),
                min_cash_reserve=Decimal("1000"),
            )
        ),
    )

    assert result.rejected_count == 1
    assert result.intent_count == 1
    assert result.fill_count == 0


def test_no_intent_completes_pending_target_without_retries() -> None:
    result = run_backtest(
        bars_from_closes(["3", "2", "1", "4", "5", "6", "7"]),
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(target_weight=Decimal("0")),
    )

    assert result.bullish_signal_count == 1
    assert result.intent_count == 0
    assert result.fill_count == 0


def test_new_bearish_signal_replaces_pending_bullish_target() -> None:
    bars = bars_from_closes(
        ["3", "2", "1", "4", "0", "0", "1"],
        opens={4: "100", 5: "100", 6: "100"},
    )
    result = run_backtest(
        bars,
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(
            risk_limits=RiskLimits(
                max_order_amount=Decimal("100"),
                max_instrument_weight=Decimal("1"),
                min_cash_reserve=Decimal("0"),
            )
        ),
    )

    assert [fill.side for fill in result.fills] == [
        OrderSide.BUY,
        OrderSide.BUY,
        OrderSide.SELL,
    ]
    assert [fill.quantity for fill in result.fills] == [
        Decimal("1"),
        Decimal("1"),
        Decimal("2"),
    ]
    assert result.final_position_quantity == Decimal("0")


def test_bullish_pending_stops_instead_of_selling_after_overshoot() -> None:
    bars = bars_from_closes(
        ["3", "2", "1", "4", "5", "6", "7"],
        opens={4: "100", 5: "100", 6: "200"},
    )
    result = run_backtest(
        bars,
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(
            quantity_step=Decimal("0.1"),
            risk_limits=RiskLimits(
                max_order_amount=Decimal("200"),
                max_instrument_weight=Decimal("1"),
                min_cash_reserve=Decimal("0"),
            ),
        ),
    )

    assert [fill.side for fill in result.fills] == [OrderSide.BUY, OrderSide.BUY]
    assert result.intent_count == 3
    assert result.fill_count == 2


def test_small_buy_is_skipped_and_zero_threshold_preserves_it() -> None:
    bars = bars_from_closes(
        ["3", "2", "1", "4", "5", "6", "7"],
        opens={4: "100", 5: "100", 6: "100"},
    )
    limits = RiskLimits(
        max_order_amount=Decimal("249"),
        max_instrument_weight=Decimal("1"),
        min_cash_reserve=Decimal("0"),
    )
    strategy = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)

    filtered = run_backtest(
        bars,
        strategy,
        config(
            quantity_step=Decimal("0.01"),
            min_trade_amount=Decimal("10"),
            risk_limits=limits,
        ),
    )
    compatible = run_backtest(
        bars,
        strategy,
        config(
            quantity_step=Decimal("0.01"),
            min_trade_amount=Decimal("0"),
            risk_limits=limits,
        ),
    )

    assert [fill.quantity for fill in filtered.fills] == [Decimal("2.49"), Decimal("2.49")]
    assert [fill.quantity for fill in compatible.fills] == [
        Decimal("2.49"),
        Decimal("2.49"),
        Decimal("0.02"),
    ]
    assert filtered.intent_count == 3
    assert filtered.adjusted_count == 2


def test_small_bearish_liquidation_sell_is_allowed() -> None:
    result = run_backtest(
        bars_from_closes(
            ["3", "2", "1", "4", "0", "0", "1"],
            opens={4: "100", 6: "1"},
        ),
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(min_trade_amount=Decimal("10")),
    )

    assert result.fills[-1].side is OrderSide.SELL
    assert result.fills[-1].quantity * result.fills[-1].fill_price == Decimal("5")
    assert result.final_position_quantity == Decimal("0")


def test_bearish_pending_stops_if_sizing_returns_buy() -> None:
    bars = bars_from_closes(
        ["3", "2", "1", "4", "0", "0", "1"],
        opens={4: "100", 6: "80"},
    )

    def sizing_with_wrong_bearish_direction(**kwargs):
        if kwargs["timestamp"] == bars[6].timestamp:
            return OrderIntent(
                instrument=kwargs["instrument"],
                timestamp=kwargs["timestamp"],
                strategy_id=kwargs["strategy_id"],
                side=OrderSide.BUY,
                quantity=Decimal("1"),
            )
        return create_target_weight_order_intent(**kwargs)

    with patch(
        "investing_plz.backtest.runner.create_target_weight_order_intent",
        side_effect=sizing_with_wrong_bearish_direction,
    ):
        result = run_backtest(
            bars,
            MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
            config(),
        )

    assert [fill.side for fill in result.fills] == [OrderSide.BUY]
    assert result.intent_count == 2


@pytest.mark.parametrize("value", [Decimal("-1"), -1.0])
def test_invalid_min_trade_amount_is_rejected(value) -> None:
    expected = ValueError if isinstance(value, Decimal) else TypeError
    with pytest.raises(expected):
        config(min_trade_amount=value)


def test_buy_uses_adverse_slippage_and_fee_aware_cash_accounting() -> None:
    bars = bars_from_closes(["3", "2", "1", "4", "5"], opens={4: "100"})
    result = run_backtest(
        bars,
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(fee_rate=Decimal("0.01"), slippage_bps=Decimal("100")),
    )

    fill = result.fills[0]
    assert fill.timestamp == bars[4].timestamp
    assert fill.fill_price == Decimal("101.00")
    assert fill.fill_price > bars[4].open
    assert fill.fee_amount == Decimal("5.0500")
    assert result.final_cash == Decimal("489.9500")
    assert result.final_position_quantity == Decimal("5")


def test_sell_uses_adverse_slippage_and_net_fee_proceeds() -> None:
    bars = bars_from_closes(
        ["3", "2", "1", "4", "0", "0", "1"],
        opens={4: "100", 6: "80"},
    )
    result = run_backtest(
        bars,
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(fee_rate=Decimal("0.01"), slippage_bps=Decimal("100")),
    )

    sell = result.fills[-1]
    assert sell.side is OrderSide.SELL
    assert sell.fill_price == Decimal("79.20")
    assert sell.fill_price < bars[6].open
    assert sell.fee_amount == Decimal("3.9600")
    assert result.final_cash == Decimal("881.9900")
    assert result.final_position_quantity == Decimal("0")


def test_risk_uses_slippage_adjusted_fill_price() -> None:
    result = run_backtest(
        bars_from_closes(["3", "2", "1", "4", "5"], opens={4: "100"}),
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(
            slippage_bps=Decimal("100"),
            risk_limits=RiskLimits(
                max_order_amount=Decimal("500"),
                max_instrument_weight=Decimal("1"),
                min_cash_reserve=Decimal("0"),
            ),
        ),
    )

    assert result.adjusted_count == 1
    assert result.fills[0].fill_price == Decimal("101.00")
    assert result.fills[0].quantity == Decimal("4")
    assert result.fills[0].quantity * result.fills[0].fill_price <= Decimal("500")


def test_fee_aware_affordability_rounds_down_and_preserves_cash_reserve() -> None:
    result = run_backtest(
        bars_from_closes(["3", "2", "1", "4", "5", "6", "7"], opens={4: "100"}),
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(
            target_weight=Decimal("1"),
            fee_rate=Decimal("0.10"),
            risk_limits=RiskLimits(
                max_order_amount=Decimal("10000"),
                max_instrument_weight=Decimal("1"),
                min_cash_reserve=Decimal("100"),
            ),
        ),
    )

    assert result.fills[0].quantity == Decimal("8")
    assert result.fills[0].fee_amount == Decimal("80.00")
    assert result.final_cash == Decimal("120.00")
    assert result.final_cash >= Decimal("100")
    assert result.final_cash >= Decimal("0")
    assert result.fill_count == 1


def test_zero_cost_settings_match_legacy_defaults() -> None:
    bars = bars_from_closes(
        ["3", "2", "1", "4", "0", "0", "1"],
        opens={4: "100", 6: "80"},
    )
    strategy = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)

    legacy = run_backtest(bars, strategy, config())
    explicit_zero = run_backtest(
        bars,
        strategy,
        config(fee_rate=Decimal("0"), slippage_bps=Decimal("0")),
    )

    assert explicit_zero == legacy
    assert all(fill.fee_amount == Decimal("0") for fill in explicit_zero.fills)


def test_cost_aware_backtest_is_deterministic() -> None:
    bars = bars_from_closes(
        ["3", "2", "1", "4", "0", "0", "1"],
        opens={4: "100", 6: "80"},
    )
    strategy = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)
    cost_config = config(fee_rate=Decimal("0.001"), slippage_bps=Decimal("5"))

    assert run_backtest(bars, strategy, cost_config) == run_backtest(
        bars, strategy, cost_config
    )


def test_risk_rejected_creates_no_fill() -> None:
    result = run_backtest(
        bars_from_closes(["3", "2", "1", "4", "5"], opens={4: "100"}),
        MovingAverageCrossoverStrategy(fast_window=2, slow_window=3),
        config(
            risk_limits=RiskLimits(
                max_order_amount=Decimal("10000"),
                max_instrument_weight=Decimal("1"),
                min_cash_reserve=Decimal("1000"),
            )
        ),
    )

    assert result.intent_count == 1
    assert result.rejected_count == 1
    assert result.fill_count == 0


def test_portfolio_buy_and_sell_updates_cash_and_quantity() -> None:
    timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
    portfolio = BacktestPortfolio(cash=Decimal("1000"))
    portfolio = portfolio.apply(
        Fill(INSTRUMENT, timestamp, OrderSide.BUY, Decimal("5"), Decimal("100"), "test")
    )
    assert portfolio == BacktestPortfolio(
        cash=Decimal("500"),
        position_quantity=Decimal("5"),
        average_cost=Decimal("100"),
    )

    portfolio = portfolio.apply(
        Fill(INSTRUMENT, timestamp, OrderSide.SELL, Decimal("2"), Decimal("120"), "test")
    )
    assert portfolio == BacktestPortfolio(
        cash=Decimal("740"),
        position_quantity=Decimal("3"),
        average_cost=Decimal("100"),
        realized_pnl=Decimal("40"),
    )


def test_portfolio_prevents_selling_more_than_is_held() -> None:
    portfolio = BacktestPortfolio(cash=Decimal("100"), position_quantity=Decimal("1"))
    fill = Fill(
        INSTRUMENT,
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        OrderSide.SELL,
        Decimal("2"),
        Decimal("100"),
        "test",
    )

    with pytest.raises(ValueError, match="exceeds the current position"):
        portfolio.apply(fill)


def test_fill_rejects_float_financial_values() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        Fill(
            INSTRUMENT,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            OrderSide.BUY,
            0.1,  # type: ignore[arg-type]
            Decimal("100"),
            "test",
        )


def test_fill_requires_utc_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Fill(
            INSTRUMENT,
            datetime(2024, 1, 1),
            OrderSide.BUY,
            Decimal("1"),
            Decimal("100"),
            "test",
        )


def test_same_inputs_produce_identical_results() -> None:
    bars = bars_from_closes(
        ["3", "2", "1", "4", "0", "0", "1"], opens={4: "100", 6: "80"}
    )
    strategy = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)

    assert run_backtest(bars, strategy, config()) == run_backtest(bars, strategy, config())
