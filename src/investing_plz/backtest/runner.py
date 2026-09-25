from collections.abc import Sequence
from decimal import Decimal

from investing_plz.application.position_sizing import (
    create_target_weight_order_intent,
)
from investing_plz.backtest.costs import apply_slippage, calculate_fee
from investing_plz.backtest.models import (
    BacktestConfig,
    BacktestPortfolio,
    BacktestResult,
    Fill,
)
from investing_plz.domain import Bar, OrderSide
from investing_plz.domain.decimal import round_down_to_step
from investing_plz.risk import BasicRiskManager, RiskContext, RiskStatus
from investing_plz.strategy import MovingAverageCrossoverStrategy, SignalType


def run_backtest(
    bars: Sequence[Bar],
    strategy: MovingAverageCrossoverStrategy,
    config: BacktestConfig,
) -> BacktestResult:
    """Replay closed bars and execute each actionable signal at the next open."""

    _validate_bars(bars)
    portfolio = BacktestPortfolio(cash=config.initial_cash)
    risk_manager = BasicRiskManager()
    desired_target_weight = Decimal("0")
    rebalance_pending = False
    pending_direction: OrderSide | None = None
    target_strategy_id = strategy.strategy_id
    fills: list[Fill] = []
    signal_count = bullish_count = bearish_count = 0
    intent_count = approved_count = adjusted_count = rejected_count = 0

    for index, bar in enumerate(bars):
        if rebalance_pending:
            portfolio_value = portfolio.value_at(bar.open)
            intent = create_target_weight_order_intent(
                instrument=bar.instrument,
                timestamp=bar.timestamp,
                strategy_id=target_strategy_id,
                target_weight=desired_target_weight,
                portfolio_value=portfolio_value,
                current_price=bar.open,
                current_quantity=portfolio.position_quantity,
                quantity_step=config.quantity_step,
            )
            if intent is None:
                rebalance_pending = False
            else:
                intent_count += 1
                if intent.side is not pending_direction:
                    rebalance_pending = False
                elif (
                    pending_direction is OrderSide.BUY
                    and intent.quantity * bar.open < config.min_trade_amount
                ):
                    rebalance_pending = False
                else:
                    fill_price = apply_slippage(
                        bar.open,
                        intent.side,
                        config.slippage_bps,
                    )
                    risk_portfolio_value = portfolio.value_at(fill_price)
                    decision = risk_manager.evaluate(
                        intent,
                        RiskContext(
                            portfolio_value=risk_portfolio_value,
                            available_cash=portfolio.cash,
                            current_position_value=(
                                portfolio.position_quantity * fill_price
                            ),
                            current_price=fill_price,
                            quantity_step=config.quantity_step,
                        ),
                        config.risk_limits,
                    )
                    if decision.status is RiskStatus.APPROVED:
                        approved_count += 1
                        rebalance_pending = False
                    elif decision.status is RiskStatus.ADJUSTED:
                        adjusted_count += 1
                        rebalance_pending = True
                    else:
                        rejected_count += 1
                        rebalance_pending = False

                    if decision.approved_intent is not None:
                        approved_intent = decision.approved_intent
                        fill_quantity = approved_intent.quantity
                        affordability_reduced = False
                        if approved_intent.side is OrderSide.BUY:
                            available_spend = max(
                                Decimal("0"),
                                portfolio.cash - config.risk_limits.min_cash_reserve,
                            )
                            per_unit_cost = fill_price * (
                                Decimal("1") + config.fee_rate
                            )
                            affordable_quantity = round_down_to_step(
                                available_spend / per_unit_cost,
                                config.quantity_step,
                            )
                            if affordable_quantity < fill_quantity:
                                fill_quantity = affordable_quantity
                                affordability_reduced = True

                        if fill_quantity == 0:
                            rebalance_pending = False
                        else:
                            fee_amount = calculate_fee(
                                fill_quantity,
                                fill_price,
                                config.fee_rate,
                            )
                            fill = Fill(
                                instrument=approved_intent.instrument,
                                timestamp=bar.timestamp,
                                side=approved_intent.side,
                                quantity=fill_quantity,
                                fill_price=fill_price,
                                strategy_id=approved_intent.strategy_id,
                                fee_amount=fee_amount,
                            )
                            portfolio = portfolio.apply(fill)
                            fills.append(fill)
                            if affordability_reduced:
                                rebalance_pending = False

        history = bars[: index + 1]
        if len(history) < strategy.minimum_bars:
            continue
        signal = strategy.generate_signal(history)
        signal_count += 1
        if signal.signal_type is SignalType.BULLISH_CROSSOVER:
            bullish_count += 1
            desired_target_weight = config.target_weight
            rebalance_pending = True
            pending_direction = OrderSide.BUY
            target_strategy_id = signal.strategy_id
        elif signal.signal_type is SignalType.BEARISH_CROSSOVER:
            bearish_count += 1
            desired_target_weight = Decimal("0")
            rebalance_pending = True
            pending_direction = OrderSide.SELL
            target_strategy_id = signal.strategy_id

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
