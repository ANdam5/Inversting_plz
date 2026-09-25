from collections.abc import Sequence
from decimal import Decimal

from investing_plz.application.position_sizing import (
    create_target_weight_order_intent,
)
from investing_plz.backtest.models import (
    BacktestConfig,
    BacktestPortfolio,
    BacktestResult,
    Fill,
)
from investing_plz.domain import Bar
from investing_plz.risk import BasicRiskManager, RiskContext, RiskStatus
from investing_plz.strategy import MovingAverageCrossoverStrategy, Signal, SignalType


def run_backtest(
    bars: Sequence[Bar],
    strategy: MovingAverageCrossoverStrategy,
    config: BacktestConfig,
) -> BacktestResult:
    """Replay closed bars and execute each actionable signal at the next open."""

    _validate_bars(bars)
    portfolio = BacktestPortfolio(cash=config.initial_cash)
    risk_manager = BasicRiskManager()
    pending_signal: Signal | None = None
    fills: list[Fill] = []
    signal_count = bullish_count = bearish_count = 0
    intent_count = approved_count = adjusted_count = rejected_count = 0

    for index, bar in enumerate(bars):
        if pending_signal is not None:
            target_weight = (
                config.target_weight
                if pending_signal.signal_type is SignalType.BULLISH_CROSSOVER
                else Decimal("0")
            )
            portfolio_value = portfolio.value_at(bar.open)
            intent = create_target_weight_order_intent(
                instrument=bar.instrument,
                timestamp=bar.timestamp,
                strategy_id=pending_signal.strategy_id,
                target_weight=target_weight,
                portfolio_value=portfolio_value,
                current_price=bar.open,
                current_quantity=portfolio.position_quantity,
                quantity_step=config.quantity_step,
            )
            if intent is not None:
                intent_count += 1
                decision = risk_manager.evaluate(
                    intent,
                    RiskContext(
                        portfolio_value=portfolio_value,
                        available_cash=portfolio.cash,
                        current_position_value=portfolio.position_quantity * bar.open,
                        current_price=bar.open,
                        quantity_step=config.quantity_step,
                    ),
                    config.risk_limits,
                )
                if decision.status is RiskStatus.APPROVED:
                    approved_count += 1
                elif decision.status is RiskStatus.ADJUSTED:
                    adjusted_count += 1
                else:
                    rejected_count += 1

                if decision.approved_intent is not None:
                    approved_intent = decision.approved_intent
                    fill = Fill(
                        instrument=approved_intent.instrument,
                        timestamp=bar.timestamp,
                        side=approved_intent.side,
                        quantity=approved_intent.quantity,
                        fill_price=bar.open,
                        strategy_id=approved_intent.strategy_id,
                    )
                    portfolio = portfolio.apply(fill)
                    fills.append(fill)
            pending_signal = None

        history = bars[: index + 1]
        if len(history) < strategy.minimum_bars:
            continue
        signal = strategy.generate_signal(history)
        signal_count += 1
        if signal.signal_type is SignalType.BULLISH_CROSSOVER:
            bullish_count += 1
            pending_signal = signal
        elif signal.signal_type is SignalType.BEARISH_CROSSOVER:
            bearish_count += 1
            pending_signal = signal

    final_price = bars[-1].close
    final_market_value = portfolio.position_quantity * final_price
    return BacktestResult(
        initial_cash=config.initial_cash,
        final_cash=portfolio.cash,
        final_position_quantity=portfolio.position_quantity,
        final_position_market_value=final_market_value,
        final_portfolio_value=portfolio.cash + final_market_value,
        signal_count=signal_count,
        bullish_signal_count=bullish_count,
        bearish_signal_count=bearish_count,
        intent_count=intent_count,
        approved_count=approved_count,
        adjusted_count=adjusted_count,
        rejected_count=rejected_count,
        fills=tuple(fills),
    )


def _validate_bars(bars: Sequence[Bar]) -> None:
    if not bars:
        raise ValueError("backtest requires at least one closed bar")
    instrument = bars[0].instrument
    interval = bars[0].interval
    if any(bar.instrument != instrument or bar.interval != interval for bar in bars):
        raise ValueError("all bars must have the same instrument and interval")
    timestamps = [bar.timestamp for bar in bars]
    if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
        raise ValueError("bars must have unique timestamps in ascending order")
