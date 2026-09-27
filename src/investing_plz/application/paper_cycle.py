from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
import logging

from investing_plz.application.position_sizing import (
    create_target_weight_order_intent,
)
from investing_plz.broker import ExecutionFill, PaperBroker
from investing_plz.clock import Clock
from investing_plz.domain import Bar, Order, OrderIntent, OrderSide
from investing_plz.domain.decimal import require_decimal
from investing_plz.domain.time import require_utc
from investing_plz.execution import (
    apply_slippage,
    validate_fee_rate,
    validate_slippage_bps,
)
from investing_plz.risk import RiskContext, RiskDecision, RiskLimits, RiskManager
from investing_plz.storage.paper import (
    PaperCursorScope,
    PaperDecisionKey,
    PaperRepository,
)
from investing_plz.strategy import Signal, SignalType, Strategy
from investing_plz.structured_logging import log_event


_LOGGER = logging.getLogger(__name__)


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
    fee_rate: Decimal = Decimal("0"),
    slippage_bps: Decimal = Decimal("0"),
    fill_id_factory: Callable[[], str],
    clock: Clock,
    repository: PaperRepository | None = None,
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
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
    )
    cycle_time = require_utc(clock.now())
    signal = strategy.generate_signal(bars)
    instrument = bars[-1].instrument
    if signal.instrument != instrument:
        raise ValueError("strategy signal instrument must match the paper session")

    if signal.signal_type is SignalType.NEUTRAL:
        log_event(
            _LOGGER,
            "paper.neutral_no_order",
            instrument=str(instrument),
            strategy_id=signal.strategy_id,
            timeframe=bars[-1].interval,
            bar_timestamp=bars[-1].timestamp.isoformat(),
        )
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
        log_event(_LOGGER, "paper.no_order_required", strategy_id=signal.strategy_id)
        return PaperCycleResult(signal, None, None, None, None)
    expected_fill_price = apply_slippage(
        execution_reference_price,
        intent.side,
        slippage_bps,
    )
    risk_position_value = current_quantity * expected_fill_price
    risk_portfolio_value = broker.cash + risk_position_value

    decision = risk_manager.evaluate(
        intent,
        RiskContext(
            portfolio_value=risk_portfolio_value,
            available_cash=broker.cash,
            current_position_value=risk_position_value,
            current_price=expected_fill_price,
            quantity_step=quantity_step,
            fee_rate=fee_rate,
        ),
        risk_limits,
    )
    if decision.approved_intent is None:
        log_event(
            _LOGGER,
            "paper.risk_rejected",
            strategy_id=signal.strategy_id,
            risk_status=decision.status.value,
        )
        return PaperCycleResult(signal, intent, decision, None, None)
    log_event(
        _LOGGER,
        "paper.risk_decision",
        strategy_id=signal.strategy_id,
        risk_status=decision.status.value,
    )
    if (
        decision.approved_intent.side is OrderSide.BUY
        and decision.approved_intent.quantity * expected_fill_price
        < min_trade_amount
    ):
        log_event(_LOGGER, "paper.minimum_trade_blocked", strategy_id=signal.strategy_id)
        return PaperCycleResult(signal, intent, decision, None, None)

    decision_scope = PaperCursorScope(
        instrument=instrument,
        strategy_id=signal.strategy_id,
        timeframe=bars[-1].interval,
    )
    decision_key = PaperDecisionKey(
        scope=decision_scope,
        closed_bar_timestamp=bars[-1].timestamp,
    )
    if repository is not None:
        existing = repository.get_order_for_decision(decision_key)
        if existing is not None:
            log_event(
                _LOGGER,
                "paper.duplicate_decision_blocked",
                order_id=existing.order_id,
                order_status=existing.status.value,
            )
            return PaperCycleResult(signal, intent, decision, existing, None)
        pending = repository.find_open_order_for_scope(decision_scope)
        if pending is not None:
            log_event(
                _LOGGER,
                "paper.pending_order_blocked",
                order_id=pending.order_id,
                order_status=pending.status.value,
            )
            return PaperCycleResult(signal, intent, decision, pending, None)

    submitted = broker.submit(decision.approved_intent)
    if repository is not None:
        repository.register_order_submission(decision_key, submitted)
    fill = broker.execute_order(
        submitted.order_id,
        reference_price=execution_reference_price,
        fill_id=fill_id_factory(),
        filled_at=cycle_time,
    )
    final_order = broker.get_order(submitted.order_id)
    assert final_order is not None
    if repository is not None:
        repository.save_execution(final_order, fill)
        log_event(
            _LOGGER,
            "paper.execution_persisted",
            order_id=final_order.order_id,
            fill_id=None if fill is None else fill.fill_id,
            order_status=final_order.status.value,
        )
    return PaperCycleResult(signal, intent, decision, final_order, fill)


def _validate_inputs(
    bars: Sequence[Bar],
    *,
    target_weight: Decimal,
    quantity_step: Decimal,
    min_trade_amount: Decimal,
    execution_reference_price: Decimal,
    fee_rate: Decimal,
    slippage_bps: Decimal,
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
    validate_fee_rate(fee_rate)
    validate_slippage_bps(slippage_bps)
    if not Decimal("0") <= target_weight <= Decimal("1"):
        raise ValueError("target_weight must be between 0 and 1")
    if quantity_step <= 0:
        raise ValueError("quantity_step must be greater than zero")
    if min_trade_amount < 0:
        raise ValueError("min_trade_amount must not be negative")
    if execution_reference_price <= 0:
        raise ValueError("execution_reference_price must be greater than zero")
