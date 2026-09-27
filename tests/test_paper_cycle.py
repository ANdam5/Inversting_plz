from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from investing_plz.application import PaperCycleResult, run_paper_cycle
from investing_plz.broker import PaperBroker
from investing_plz.clock import FixedClock
from investing_plz.domain import Bar, Instrument, OrderIntent, OrderSide, OrderStatus
from investing_plz.risk import BasicRiskManager, RiskLimits, RiskStatus
from investing_plz.strategy import Signal, SignalType


INSTRUMENT = Instrument("upbit", "KRW-BTC")
BAR_TIME = datetime(2026, 9, 25, tzinfo=timezone.utc)
CYCLE_TIME = datetime(2026, 9, 26, tzinfo=timezone.utc)


class FixedSignalStrategy:
    strategy_id = "fixed_signal_strategy"

    def __init__(self, signal_type: SignalType) -> None:
        self.signal_type = signal_type

    def generate_signal(self, bars: Sequence[Bar]) -> Signal:
        latest = bars[-1]
        return Signal(
            instrument=latest.instrument,
            timestamp=latest.timestamp,
            signal_type=self.signal_type,
            strategy_id=self.strategy_id,
        )


def make_bars(*, close: Decimal = Decimal("90")) -> list[Bar]:
    return [
        Bar(
            instrument=INSTRUMENT,
            interval="day",
            timestamp=BAR_TIME,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=Decimal("1"),
        )
    ]


def make_broker(
    *,
    initial_cash: Decimal = Decimal("1000"),
    fee_rate: Decimal = Decimal("0"),
    slippage_bps: Decimal = Decimal("0"),
) -> PaperBroker:
    order_ids = iter(("order-1", "order-2", "order-3"))
    return PaperBroker(
        initial_cash=initial_cash,
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
        order_id_factory=lambda: next(order_ids),
        submitted_at_factory=lambda: CYCLE_TIME,
    )


def limits(
    *,
    max_order_amount: Decimal = Decimal("1000"),
    max_instrument_weight: Decimal = Decimal("1"),
    min_cash_reserve: Decimal = Decimal("0"),
) -> RiskLimits:
    return RiskLimits(
        max_order_amount=max_order_amount,
        max_instrument_weight=max_instrument_weight,
        min_cash_reserve=min_cash_reserve,
    )


def cycle(
    broker: PaperBroker,
    signal_type: SignalType,
    *,
    risk_limits: RiskLimits | None = None,
    target_weight: Decimal = Decimal("0.5"),
    reference_price: Decimal = Decimal("100"),
    fill_id: str = "fill-1",
    min_trade_amount: Decimal = Decimal("0"),
    fee_rate: Decimal = Decimal("0"),
    slippage_bps: Decimal = Decimal("0"),
) -> PaperCycleResult:
    return run_paper_cycle(
        make_bars(),
        FixedSignalStrategy(signal_type),
        broker,
        BasicRiskManager(),
        risk_limits or limits(),
        target_weight=target_weight,
        quantity_step=Decimal("1"),
        min_trade_amount=min_trade_amount,
        execution_reference_price=reference_price,
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
        fill_id_factory=lambda: fill_id,
        clock=FixedClock(CYCLE_TIME),
    )


def seed_position(broker: PaperBroker, quantity: Decimal = Decimal("5")) -> None:
    order = broker.submit(
        OrderIntent(
            instrument=INSTRUMENT,
            timestamp=CYCLE_TIME,
            strategy_id="seed",
            side=OrderSide.BUY,
            quantity=quantity,
        )
    )
    fill = broker.execute_order(
        order.order_id,
        reference_price=Decimal("100"),
        fill_id="seed-fill",
        filled_at=CYCLE_TIME,
    )
    assert fill is not None


def test_bullish_cycle_buys_through_risk_and_paper_execution() -> None:
    broker = make_broker()

    result = cycle(broker, SignalType.BULLISH_CROSSOVER)

    assert result.order_intent is not None
    assert result.order_intent.side is OrderSide.BUY
    assert result.order_intent.quantity == Decimal("5")
    assert result.risk_decision is not None
    assert result.risk_decision.status is RiskStatus.APPROVED
    assert result.order is not None
    assert result.order.status is OrderStatus.FILLED
    assert result.fill is not None
    assert broker.cash == Decimal("500")
    assert broker.position_quantity(INSTRUMENT) == Decimal("5")


def test_bearish_cycle_sells_existing_position_to_zero() -> None:
    broker = make_broker()
    seed_position(broker)

    result = cycle(
        broker,
        SignalType.BEARISH_CROSSOVER,
        fill_id="fill-2",
        reference_price=Decimal("110"),
    )

    assert result.order_intent is not None
    assert result.order_intent.side is OrderSide.SELL
    assert result.fill is not None
    assert result.fill.side is OrderSide.SELL
    assert broker.position_quantity(INSTRUMENT) == Decimal("0")
    assert broker.cash == Decimal("1050")


def test_neutral_cycle_does_not_rebalance_or_change_account() -> None:
    broker = make_broker()
    seed_position(broker)
    cash = broker.cash
    position = broker.position_quantity(INSTRUMENT)
    fills = broker.list_fills()

    result = cycle(broker, SignalType.NEUTRAL, fill_id="unused")

    assert result.order_intent is None
    assert result.risk_decision is None
    assert result.order is None
    assert result.fill is None
    assert broker.cash == cash
    assert broker.position_quantity(INSTRUMENT) == position
    assert broker.list_fills() == fills


def test_risk_rejected_cycle_never_submits_to_broker() -> None:
    broker = make_broker()

    result = cycle(
        broker,
        SignalType.BULLISH_CROSSOVER,
        risk_limits=limits(min_cash_reserve=Decimal("1000")),
    )

    assert result.risk_decision is not None
    assert result.risk_decision.status is RiskStatus.REJECTED
    assert result.order is None
    assert result.fill is None
    assert broker.list_open_orders() == ()
    assert broker.list_fills() == ()


def test_risk_adjusted_quantity_is_submitted_and_filled() -> None:
    broker = make_broker()

    result = cycle(
        broker,
        SignalType.BULLISH_CROSSOVER,
        target_weight=Decimal("1"),
        risk_limits=limits(max_order_amount=Decimal("300")),
    )

    assert result.order_intent is not None
    assert result.order_intent.quantity == Decimal("10")
    assert result.risk_decision is not None
    assert result.risk_decision.status is RiskStatus.ADJUSTED
    assert result.risk_decision.approved_intent is not None
    assert result.risk_decision.approved_intent.quantity == Decimal("3")
    assert result.order is not None
    assert result.order.quantity == Decimal("3")
    assert result.fill is not None
    assert result.fill.quantity == Decimal("3")


def test_fee_aware_risk_preserves_minimum_cash_reserve_after_fill() -> None:
    broker = make_broker(fee_rate=Decimal("0.10"))

    result = cycle(
        broker,
        SignalType.BULLISH_CROSSOVER,
        target_weight=Decimal("1"),
        risk_limits=limits(min_cash_reserve=Decimal("100")),
        fee_rate=Decimal("0.10"),
    )

    assert result.risk_decision is not None
    assert result.risk_decision.status is RiskStatus.ADJUSTED
    assert result.risk_decision.approved_intent is not None
    assert result.risk_decision.approved_intent.quantity == Decimal("8")
    assert result.order is not None
    assert result.order.status is OrderStatus.FILLED
    assert result.fill is not None
    assert broker.cash == Decimal("120.00")
    assert broker.cash >= Decimal("100")
    assert broker.position_quantity(INSTRUMENT) == Decimal("8")


def test_slippage_adjusted_risk_keeps_fill_notional_within_max_order_amount() -> None:
    broker = make_broker(slippage_bps=Decimal("100"))

    result = cycle(
        broker,
        SignalType.BULLISH_CROSSOVER,
        target_weight=Decimal("1"),
        risk_limits=limits(max_order_amount=Decimal("500")),
        slippage_bps=Decimal("100"),
    )

    assert result.order_intent is not None
    assert result.order_intent.quantity == Decimal("10")
    assert result.risk_decision is not None
    assert result.risk_decision.status is RiskStatus.ADJUSTED
    assert result.order is not None
    assert result.order.quantity == Decimal("4")
    assert result.fill is not None
    assert result.fill.fill_price == Decimal("101.00")
    assert result.fill.quantity * result.fill.fill_price <= Decimal("500")


def test_minimum_trade_amount_is_checked_after_risk_adjustment() -> None:
    broker = make_broker()

    result = cycle(
        broker,
        SignalType.BULLISH_CROSSOVER,
        target_weight=Decimal("1"),
        risk_limits=limits(max_order_amount=Decimal("300")),
        min_trade_amount=Decimal("400"),
    )

    assert result.order_intent is not None
    assert result.order_intent.quantity == Decimal("10")
    assert result.risk_decision is not None
    assert result.risk_decision.status is RiskStatus.ADJUSTED
    assert result.risk_decision.approved_intent is not None
    assert result.risk_decision.approved_intent.quantity == Decimal("3")
    assert result.order is None
    assert result.fill is None
    assert broker.list_open_orders() == ()
    assert broker.list_fills() == ()


def test_small_bearish_liquidation_ignores_minimum_buy_trade_amount() -> None:
    broker = make_broker()
    seed_position(broker, Decimal("1"))

    result = cycle(
        broker,
        SignalType.BEARISH_CROSSOVER,
        reference_price=Decimal("100"),
        fill_id="fill-2",
        min_trade_amount=Decimal("500"),
    )

    assert result.order_intent is not None
    assert result.order_intent.side is OrderSide.SELL
    assert result.fill is not None
    assert result.fill.quantity == Decimal("1")
    assert broker.position_quantity(INSTRUMENT) == Decimal("0")


def test_explicit_reference_price_not_latest_close_drives_sizing_and_fill() -> None:
    broker = make_broker()

    result = cycle(
        broker,
        SignalType.BULLISH_CROSSOVER,
        reference_price=Decimal("100"),
    )

    assert make_bars()[0].close == Decimal("90")
    assert result.order_intent is not None
    assert result.order_intent.quantity == Decimal("5")
    assert result.fill is not None
    assert result.fill.fill_price == Decimal("100")


def test_paper_broker_applies_fee_and_slippage_once() -> None:
    broker = make_broker(
        fee_rate=Decimal("0.001"),
        slippage_bps=Decimal("10"),
    )

    result = cycle(
        broker,
        SignalType.BULLISH_CROSSOVER,
        fee_rate=Decimal("0.001"),
        slippage_bps=Decimal("10"),
    )

    assert result.fill is not None
    assert result.fill.fill_price == Decimal("100.100")
    assert result.fill.fee_amount == Decimal("0.500500")
    assert broker.cash == Decimal("498.999500")


def test_explicit_zero_fee_and_slippage_match_existing_paper_behavior() -> None:
    default_broker = make_broker()
    explicit_zero_broker = make_broker(
        fee_rate=Decimal("0"),
        slippage_bps=Decimal("0"),
    )

    default_result = cycle(default_broker, SignalType.BULLISH_CROSSOVER)
    explicit_zero_result = cycle(
        explicit_zero_broker,
        SignalType.BULLISH_CROSSOVER,
        fee_rate=Decimal("0"),
        slippage_bps=Decimal("0"),
    )

    assert explicit_zero_result == default_result
    assert explicit_zero_broker.cash == default_broker.cash
    assert explicit_zero_broker.list_positions() == default_broker.list_positions()


def test_same_deterministic_inputs_produce_identical_cycle_results() -> None:
    first_broker = make_broker()
    second_broker = make_broker()

    first = cycle(first_broker, SignalType.BULLISH_CROSSOVER)
    second = cycle(second_broker, SignalType.BULLISH_CROSSOVER)

    assert first == second
    assert first_broker.cash == second_broker.cash
    assert first_broker.position_quantity(INSTRUMENT) == second_broker.position_quantity(
        INSTRUMENT
    )


def test_cycle_uses_fixed_clock_for_intent_and_fill_time() -> None:
    broker = make_broker()

    result = cycle(broker, SignalType.BULLISH_CROSSOVER)

    assert result.order_intent is not None
    assert result.order_intent.timestamp == CYCLE_TIME
    assert result.fill is not None
    assert result.fill.filled_at == CYCLE_TIME
