from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from investing_plz.application.position_sizing import (
    create_target_weight_order_intent,
)
from investing_plz.broker import ExecutionFill, PaperBroker
from investing_plz.clock import Clock
from investing_plz.domain import Bar, Order, OrderIntent, OrderSide
from investing_plz.domain.decimal import require_decimal
from investing_plz.domain.time import require_utc
from investing_plz.risk import RiskContext, RiskDecision, RiskLimits, RiskManager
from investing_plz.strategy import Signal, SignalType, Strategy


@dataclass(frozen=True, slots=True)
class PaperCycleResult:
    signal: Signal
    order_intent: OrderIntent | None
    risk_decision: RiskDecision | None
    order: Order | None
    fill: ExecutionFill | None


def run_paper_cycle(
    bars: Sequence[Bar],
    strategy: Strategy,
    broker: PaperBroker,
    risk_manager: RiskManager,
    risk_limits: RiskLimits,
    *,
    target_weight: Decimal,
    quantity_step: Decimal,
    min_trade_amount: Decimal,
    execution_reference_price: Decimal,
    fill_id_factory: Callable[[], str],
    clock: Clock,
) -> PaperCycleResult:
    """Run one single-instrument paper decision and execution cycle.

    ``bars`` must contain only completed candles. The caller supplies a current
    executable reference price; the latest historical close is not assumed to
    be executable.
    """

    _validate_inputs(
        bars,
        target_weight=target_weight,
        quantity_step=quantity_step,
        min_trade_amount=min_trade_amount,
        execution_reference_price=execution_reference_price,
    )
    cycle_time = require_utc(clock.now())
    signal = strategy.generate_signal(bars)
    instrument = bars[-1].instrument
    if signal.instrument != instrument:
        raise ValueError("strategy signal instrument must match the paper session")

    if signal.signal_type is SignalType.NEUTRAL:
        return PaperCycleResult(signal, None, None, None, None)

    desired_target_weight = (
        target_weight
        if signal.signal_type is SignalType.BULLISH_CROSSOVER
        else Decimal("0")
    )
    current_quantity = broker.position_quantity(instrument)
    current_position_value = current_quantity * execution_reference_price
    portfolio_value = broker.cash + current_position_value
    intent = create_target_weight_order_intent(
        instrument=instrument,
        timestamp=cycle_time,
        strategy_id=signal.strategy_id,
        target_weight=desired_target_weight,
        portfolio_value=portfolio_value,
        current_price=execution_reference_price,
        current_quantity=current_quantity,
        quantity_step=quantity_step,
    )
    if intent is None:
        return PaperCycleResult(signal, None, None, None, None)
    if (
        intent.side is OrderSide.BUY
        and intent.quantity * execution_reference_price < min_trade_amount
    ):
        return PaperCycleResult(signal, intent, None, None, None)

    decision = risk_manager.evaluate(
        intent,
        RiskContext(
            portfolio_value=portfolio_value,
            available_cash=broker.cash,
            current_position_value=current_position_value,
            current_price=execution_reference_price,
            quantity_step=quantity_step,
        ),
        risk_limits,
    )
    if decision.approved_intent is None:
        return PaperCycleResult(signal, intent, decision, None, None)

    submitted = broker.submit(decision.approved_intent)
    fill = broker.execute_order(
        submitted.order_id,
        reference_price=execution_reference_price,
        fill_id=fill_id_factory(),
        filled_at=cycle_time,
    )
    final_order = broker.get_order(submitted.order_id)
    assert final_order is not None
    return PaperCycleResult(signal, intent, decision, final_order, fill)


def _validate_inputs(
    bars: Sequence[Bar],
    *,
    target_weight: Decimal,
    quantity_step: Decimal,
    min_trade_amount: Decimal,
    execution_reference_price: Decimal,
) -> None:
    if not bars:
        raise ValueError("paper cycle requires at least one closed bar")
    instrument = bars[0].instrument
    if any(bar.instrument != instrument for bar in bars):
        raise ValueError("paper cycle supports one instrument per session")
    timestamps = [bar.timestamp for bar in bars]
    if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
        raise ValueError("bars must have unique timestamps in ascending order")

    target_weight = require_decimal(target_weight, name="target_weight")
    quantity_step = require_decimal(quantity_step, name="quantity_step")
    min_trade_amount = require_decimal(min_trade_amount, name="min_trade_amount")
    execution_reference_price = require_decimal(
        execution_reference_price,
        name="execution_reference_price",
    )
    if not Decimal("0") <= target_weight <= Decimal("1"):
        raise ValueError("target_weight must be between 0 and 1")
    if quantity_step <= 0:
        raise ValueError("quantity_step must be greater than zero")
    if min_trade_amount < 0:
        raise ValueError("min_trade_amount must not be negative")
    if execution_reference_price <= 0:
        raise ValueError("execution_reference_price must be greater than zero")
