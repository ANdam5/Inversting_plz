from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from investing_plz.application import (
    PaperPollingScheduler,
    recover_paper_runtime,
    run_paper_cycle,
)
from investing_plz.broker import ExecutionFill, PaperBroker
from investing_plz.clock import FixedClock
from investing_plz.domain import (
    Bar,
    Instrument,
    Order,
    OrderIntent,
    OrderSide,
    OrderStatus,
)
from investing_plz.risk import BasicRiskManager, RiskLimits
from investing_plz.storage import (
    PaperCursorScope,
    PaperDecisionKey,
    SQLitePaperRepository,
)
from investing_plz.strategy import Signal, SignalType


BTC = Instrument("upbit", "KRW-BTC")
ETH = Instrument("upbit", "KRW-ETH")
T0 = datetime(2026, 9, 24, tzinfo=timezone.utc)
T1 = datetime(2026, 9, 25, tzinfo=timezone.utc)
T2 = datetime(2026, 9, 26, tzinfo=timezone.utc)
SCOPE = PaperCursorScope(BTC, "ma", "day")


class BullishStrategy:
    strategy_id = "ma"

    def generate_signal(self, bars: Sequence[Bar]) -> Signal:
        return Signal(
            instrument=bars[-1].instrument,
            timestamp=bars[-1].timestamp,
            signal_type=SignalType.BULLISH_CROSSOVER,
            strategy_id=self.strategy_id,
        )


def make_order(
    order_id: str,
    *,
    instrument: Instrument = BTC,
    side: OrderSide = OrderSide.BUY,
    quantity: Decimal = Decimal("1"),
    status: OrderStatus = OrderStatus.PENDING,
    strategy_id: str = "ma",
    submitted_at: datetime = T1,
) -> Order:
    return Order(
        order_id=order_id,
        instrument=instrument,
        side=side,
        quantity=quantity,
        strategy_id=strategy_id,
        submitted_at=submitted_at,
        status=status,
    )


def make_fill(
    order: Order,
    *,
    fill_id: str,
    fill_price: Decimal,
    fee_amount: Decimal,
    filled_at: datetime = T1,
    instrument: Instrument | None = None,
) -> ExecutionFill:
    return ExecutionFill(
        fill_id=fill_id,
        order_id=order.order_id,
        instrument=instrument or order.instrument,
        side=order.side,
        quantity=order.quantity,
        fill_price=fill_price,
        fee_amount=fee_amount,
        filled_at=filled_at,
        strategy_id=order.strategy_id,
    )


def persist_execution(
    repository: SQLitePaperRepository,
    order: Order,
    fill: ExecutionFill,
    *,
    timestamp: datetime,
    timeframe: str = "day",
) -> None:
    pending = Order(
        order_id=order.order_id,
        instrument=order.instrument,
        side=order.side,
        quantity=order.quantity,
        strategy_id=order.strategy_id,
        submitted_at=order.submitted_at,
    )
    repository.register_order_submission(
        PaperDecisionKey(
            PaperCursorScope(order.instrument, order.strategy_id, timeframe),
            timestamp,
        ),
        pending,
    )
    repository.save_execution(order, fill)


def make_repository(path) -> SQLitePaperRepository:
    repository = SQLitePaperRepository(path)
    repository.initialize()
    return repository


def recover(
    repository: SQLitePaperRepository,
    *,
    initial_cash: Decimal = Decimal("1000"),
    order_ids: list[str] | None = None,
    submitted_times: list[datetime] | None = None,
):
    order_ids = order_ids if order_ids is not None else ["new-order"]
    submitted_times = submitted_times if submitted_times is not None else [T2]
    return recover_paper_runtime(
        repository,
        SCOPE,
        initial_cash=initial_cash,
        fee_rate=Decimal("0.001"),
        slippage_bps=Decimal("5"),
        order_id_factory=lambda: order_ids.pop(0),
        submitted_at_factory=lambda: submitted_times.pop(0),
    )


def make_bar(timestamp: datetime = T0) -> Bar:
    return Bar(
        instrument=BTC,
        interval="day",
        timestamp=timestamp,
        open=Decimal("100"),
        high=Decimal("100"),
        low=Decimal("100"),
        close=Decimal("100"),
        volume=Decimal("1"),
    )


def test_empty_repository_recovers_initial_cash_zero_positions_and_no_cursor(
    tmp_path,
) -> None:
    repository = make_repository(tmp_path / "paper.db")

    result = recover(repository)

    assert result.broker.cash == Decimal("1000")
    assert result.broker.position_quantity(BTC) == Decimal("0")
    assert result.broker.list_open_orders() == ()
    assert result.broker.list_fills() == ()
    assert result.last_processed_bar_timestamp is None


def test_restart_recovers_buy_account_orders_fills_cursor_without_factory_use(
    tmp_path,
) -> None:
    database = tmp_path / "paper.db"
    repository_a = make_repository(database)
    filled = make_order(
        "order-1", quantity=Decimal("2"), status=OrderStatus.FILLED
    )
    fill = make_fill(
        filled,
        fill_id="fill-1",
        fill_price=Decimal("100"),
        fee_amount=Decimal("1"),
    )
    persist_execution(repository_a, filled, fill, timestamp=T0)
    repository_a.save_last_processed_bar_timestamp(SCOPE, T0)

    repository_b = make_repository(database)
    order_ids = ["unused-order"]
    submitted_times = [T2]
    result = recover(
        repository_b,
        order_ids=order_ids,
        submitted_times=submitted_times,
    )

    assert result.broker.cash == Decimal("799")
    assert result.broker.position_quantity(BTC) == Decimal("2")
    assert result.broker.get_order("order-1") == filled
    assert result.broker.list_fills() == (fill,)
    assert result.last_processed_bar_timestamp == T0
    assert order_ids == ["unused-order"]
    assert submitted_times == [T2]


def test_multiple_buy_sell_and_instruments_recover_one_cash_pool(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    btc_buy = make_order(
        "btc-buy", quantity=Decimal("2"), status=OrderStatus.FILLED
    )
    eth_buy = make_order(
        "eth-buy",
        instrument=ETH,
        quantity=Decimal("1"),
        status=OrderStatus.FILLED,
        submitted_at=T1,
    )
    btc_sell = make_order(
        "btc-sell",
        side=OrderSide.SELL,
        quantity=Decimal("1"),
        status=OrderStatus.FILLED,
        submitted_at=T2,
    )
    executions = (
        (
            btc_buy,
            make_fill(
                btc_buy,
                fill_id="fill-1",
                fill_price=Decimal("100"),
                fee_amount=Decimal("1"),
                filled_at=T0,
            ),
            T0,
        ),
        (
            eth_buy,
            make_fill(
                eth_buy,
                fill_id="fill-2",
                fill_price=Decimal("50"),
                fee_amount=Decimal("0.5"),
                filled_at=T1,
            ),
            T1,
        ),
        (
            btc_sell,
            make_fill(
                btc_sell,
                fill_id="fill-3",
                fill_price=Decimal("120"),
                fee_amount=Decimal("0.2"),
                filled_at=T2,
            ),
            T2,
        ),
    )
    for order, fill, timestamp in executions:
        persist_execution(repository, order, fill, timestamp=timestamp)

    broker = recover(repository).broker

    assert broker.cash == Decimal("868.3")
    assert broker.position_quantity(BTC) == Decimal("1")
    assert broker.position_quantity(ETH) == Decimal("1")
    assert broker.list_fills() == tuple(item[1] for item in executions)


def test_all_order_statuses_restore_without_changing_account(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    pending = make_order("pending")
    canceled = make_order("canceled", status=OrderStatus.CANCELED)
    rejected = make_order("rejected", status=OrderStatus.REJECTED)
    repository.save_order(pending)
    repository.save_order(canceled)
    repository.save_order(rejected)

    broker = recover(repository).broker

    assert broker.get_order("pending") == pending
    assert broker.get_order("canceled") == canceled
    assert broker.get_order("rejected") == rejected
    assert broker.list_open_orders() == (pending,)
    assert broker.list_fills() == ()
    assert broker.cash == Decimal("1000")
    assert broker.position_quantity(BTC) == Decimal("0")


def test_recovered_cursor_initializes_scheduler_without_private_mutation(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    repository.save_last_processed_bar_timestamp(SCOPE, T1)
    recovery = recover(repository)

    price_calls = 0

    def price_provider() -> Decimal:
        nonlocal price_calls
        price_calls += 1
        return Decimal("100")

    scheduler = PaperPollingScheduler(
        clock=FixedClock(T2),
        poll_interval=timedelta(minutes=1),
        closed_bars_provider=lambda: [make_bar(T1)],
        execution_price_provider=price_provider,
        cycle_runner=lambda bars, price: pytest.fail("cursor must block cycle"),
        initial_last_processed_bar_timestamp=(
            recovery.last_processed_bar_timestamp
        ),
    )

    assert scheduler.last_processed_bar_timestamp == T1
    assert not scheduler.run_if_due().processed
    assert price_calls == 0


def test_scheduler_rejects_naive_initial_cursor() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        PaperPollingScheduler(
            clock=FixedClock(T2),
            poll_interval=timedelta(minutes=1),
            closed_bars_provider=lambda: [],
            execution_price_provider=lambda: Decimal("100"),
            cycle_runner=lambda bars, price: None,
            initial_last_processed_bar_timestamp=datetime(2026, 9, 25),
        )


def test_cursorless_filled_decision_recovers_and_blocks_duplicate_cycle(
    tmp_path,
) -> None:
    database = tmp_path / "paper.db"
    repository_a = make_repository(database)
    broker_a = PaperBroker(
        initial_cash=Decimal("1000"),
        order_id_factory=lambda: "order-1",
        submitted_at_factory=lambda: T1,
    )
    first = run_paper_cycle(
        [make_bar()],
        BullishStrategy(),
        broker_a,
        BasicRiskManager(),
        RiskLimits(Decimal("300"), Decimal("1"), Decimal("0")),
        target_weight=Decimal("1"),
        quantity_step=Decimal("1"),
        min_trade_amount=Decimal("0"),
        execution_reference_price=Decimal("100"),
        fill_id_factory=lambda: "fill-1",
        clock=FixedClock(T1),
        repository=repository_a,
    )
    assert first.fill is not None

    repository_b = make_repository(database)
    order_ids = ["unused-order"]
    recovery = recover(repository_b, order_ids=order_ids)
    assert recovery.last_processed_bar_timestamp is None
    fill_ids = ["unused-fill"]

    retry = run_paper_cycle(
        [make_bar()],
        BullishStrategy(),
        recovery.broker,
        BasicRiskManager(),
        RiskLimits(Decimal("300"), Decimal("1"), Decimal("0")),
        target_weight=Decimal("1"),
        quantity_step=Decimal("1"),
        min_trade_amount=Decimal("0"),
        execution_reference_price=Decimal("100"),
        fill_id_factory=lambda: fill_ids.pop(0),
        clock=FixedClock(T2),
        repository=repository_b,
    )

    assert retry.order == first.order
    assert retry.fill is None
    assert order_ids == ["unused-order"]
    assert fill_ids == ["unused-fill"]
    assert recovery.broker.cash == broker_a.cash
    assert recovery.broker.position_quantity(BTC) == Decimal("3")


def test_pending_crash_recovers_fail_closed_and_blocks_newer_decision(tmp_path) -> None:
    database = tmp_path / "paper.db"
    repository_a = make_repository(database)
    pending = make_order("pending-order")
    repository_a.register_order_submission(
        PaperDecisionKey(SCOPE, T0), pending
    )

    repository_b = make_repository(database)
    order_ids = ["unused-order"]
    recovery = recover(repository_b, order_ids=order_ids)
    assert recovery.broker.get_order(pending.order_id) == pending
    assert recovery.broker.list_open_orders() == (pending,)
    assert recovery.broker.cash == Decimal("1000")
    assert recovery.broker.position_quantity(BTC) == Decimal("0")
    fill_ids = ["unused-fill"]

    result = run_paper_cycle(
        [make_bar(T1)],
        BullishStrategy(),
        recovery.broker,
        BasicRiskManager(),
        RiskLimits(Decimal("1000"), Decimal("1"), Decimal("0")),
        target_weight=Decimal("1"),
        quantity_step=Decimal("1"),
        min_trade_amount=Decimal("0"),
        execution_reference_price=Decimal("100"),
        fill_id_factory=lambda: fill_ids.pop(0),
        clock=FixedClock(T2),
        repository=repository_b,
    )

    assert result.order == pending
    assert result.fill is None
    assert order_ids == ["unused-order"]
    assert fill_ids == ["unused-fill"]


def test_recovery_rejects_fill_order_mismatch(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    order = make_order("order-1", status=OrderStatus.FILLED)
    repository.save_order(order)
    repository.save_fill(
        make_fill(
            order,
            fill_id="fill-1",
            fill_price=Decimal("100"),
            fee_amount=Decimal("0"),
            instrument=ETH,
        )
    )

    with pytest.raises(ValueError, match="does not match"):
        recover(repository)


def test_recovery_rejects_filled_order_without_fill(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    repository.save_order(make_order("order-1", status=OrderStatus.FILLED))

    with pytest.raises(ValueError, match="exactly one persisted fill"):
        recover(repository)


def test_recovery_rejects_negative_cash_projection(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    order = make_order("order-1", quantity=Decimal("20"), status=OrderStatus.FILLED)
    fill = make_fill(
        order,
        fill_id="fill-1",
        fill_price=Decimal("100"),
        fee_amount=Decimal("0"),
    )
    persist_execution(repository, order, fill, timestamp=T0)

    with pytest.raises(ValueError, match="negative cash"):
        recover(repository)


def test_recovery_rejects_negative_position_projection(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    order = make_order(
        "order-1", side=OrderSide.SELL, status=OrderStatus.FILLED
    )
    fill = make_fill(
        order,
        fill_id="fill-1",
        fill_price=Decimal("100"),
        fee_amount=Decimal("0"),
    )
    persist_execution(repository, order, fill, timestamp=T0)

    with pytest.raises(ValueError, match="negative position"):
        recover(repository)


def test_scheduler_writes_cursor_and_reopened_runtime_skips_same_bar(
    tmp_path,
) -> None:
    database = tmp_path / "paper.db"
    repository_a = make_repository(database)
    broker_a = PaperBroker(
        initial_cash=Decimal("1000"),
        order_id_factory=lambda: "order-1",
        submitted_at_factory=lambda: T1,
    )

    def cycle_runner(bars, price):
        return run_paper_cycle(
            bars,
            BullishStrategy(),
            broker_a,
            BasicRiskManager(),
            RiskLimits(Decimal("1000"), Decimal("1"), Decimal("0")),
            target_weight=Decimal("0.3"),
            quantity_step=Decimal("1"),
            min_trade_amount=Decimal("0"),
            execution_reference_price=price,
            fill_id_factory=lambda: "fill-1",
            clock=FixedClock(T1),
            repository=repository_a,
        )

    scheduler_a = PaperPollingScheduler(
        clock=FixedClock(T1),
        poll_interval=timedelta(minutes=1),
        closed_bars_provider=lambda: [make_bar()],
        execution_price_provider=lambda: Decimal("100"),
        cycle_runner=cycle_runner,
        cursor_saver=lambda timestamp: (
            repository_a.save_last_processed_bar_timestamp(SCOPE, timestamp)
        ),
    )
    first = scheduler_a.run_if_due()
    assert first.processed
    assert first.cycle_result is not None
    assert first.cycle_result.fill is not None
    assert repository_a.get_last_processed_bar_timestamp(SCOPE) == T0

    repository_b = make_repository(database)
    recovery = recover(repository_b)
    cycle_calls = 0

    def must_not_run(bars, price):
        nonlocal cycle_calls
        cycle_calls += 1
        raise AssertionError("recovered cursor must block the same bar")

    scheduler_b = PaperPollingScheduler(
        clock=FixedClock(T2),
        poll_interval=timedelta(minutes=1),
        closed_bars_provider=lambda: [make_bar()],
        execution_price_provider=lambda: Decimal("100"),
        cycle_runner=must_not_run,
        initial_last_processed_bar_timestamp=(
            recovery.last_processed_bar_timestamp
        ),
        cursor_saver=lambda timestamp: (
            repository_b.save_last_processed_bar_timestamp(SCOPE, timestamp)
        ),
    )

    restarted = scheduler_b.run_if_due()

    assert recovery.last_processed_bar_timestamp == T0
    assert scheduler_b.last_processed_bar_timestamp == T0
    assert not restarted.processed
    assert cycle_calls == 0


def test_cursor_save_failure_retries_without_duplicate_order_or_fill(tmp_path) -> None:
    class MutableClock:
        def __init__(self, current: datetime) -> None:
            self.current = current

        def now(self) -> datetime:
            return self.current

    repository = make_repository(tmp_path / "paper.db")
    order_ids = ["order-1", "unused-order"]
    fill_ids = ["fill-1", "unused-fill"]
    broker = PaperBroker(
        initial_cash=Decimal("1000"),
        order_id_factory=lambda: order_ids.pop(0),
        submitted_at_factory=lambda: T1,
    )
    clock = MutableClock(T1)

    def cycle_runner(bars, price):
        return run_paper_cycle(
            bars,
            BullishStrategy(),
            broker,
            BasicRiskManager(),
            RiskLimits(Decimal("300"), Decimal("1"), Decimal("0")),
            target_weight=Decimal("1"),
            quantity_step=Decimal("1"),
            min_trade_amount=Decimal("0"),
            execution_reference_price=price,
            fill_id_factory=lambda: fill_ids.pop(0),
            clock=clock,
            repository=repository,
        )

    save_attempts = 0

    def cursor_saver(timestamp):
        nonlocal save_attempts
        save_attempts += 1
        if save_attempts == 1:
            raise RuntimeError("cursor write failed")
        repository.save_last_processed_bar_timestamp(SCOPE, timestamp)

    scheduler = PaperPollingScheduler(
        clock=clock,
        poll_interval=timedelta(minutes=1),
        closed_bars_provider=lambda: [make_bar()],
        execution_price_provider=lambda: Decimal("100"),
        cycle_runner=cycle_runner,
        cursor_saver=cursor_saver,
    )

    with pytest.raises(RuntimeError, match="cursor write failed"):
        scheduler.run_if_due()
    assert scheduler.last_processed_bar_timestamp is None
    assert repository.get_last_processed_bar_timestamp(SCOPE) is None
    assert len(repository.list_orders()) == 1
    assert len(repository.list_fills()) == 1

    clock.current += timedelta(minutes=1)
    retry = scheduler.run_if_due()

    assert retry.processed
    assert scheduler.last_processed_bar_timestamp == T0
    assert repository.get_last_processed_bar_timestamp(SCOPE) == T0
    assert len(repository.list_orders()) == 1
    assert len(repository.list_fills()) == 1
    assert order_ids == ["unused-order"]
    assert fill_ids == ["unused-fill"]


def test_recovered_broker_rejects_colliding_future_order_id(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    filled = make_order("order-1", status=OrderStatus.FILLED)
    persist_execution(
        repository,
        filled,
        make_fill(
            filled,
            fill_id="fill-1",
            fill_price=Decimal("100"),
            fee_amount=Decimal("0"),
        ),
        timestamp=T0,
    )
    colliding_ids = ["order-1"]
    broker = recover(repository, order_ids=colliding_ids).broker

    with pytest.raises(ValueError, match="duplicate order_id"):
        broker.submit(
            OrderIntent(
                instrument=BTC,
                timestamp=T2,
                strategy_id="other",
                side=OrderSide.BUY,
                quantity=Decimal("1"),
            )
        )

    assert broker.get_order("order-1") == filled
    assert broker.cash == Decimal("900")
    assert broker.position_quantity(BTC) == Decimal("1")
