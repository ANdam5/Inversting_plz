import sqlite3
from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from investing_plz.application import (
    PaperTradingNotReadyError,
    reconcile_paper_runtime,
    recover_paper_runtime,
    run_paper_cycle,
    run_when_paper_ready,
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
SCOPE = PaperCursorScope(BTC, "ma", "day")


class FixedStrategy:
    strategy_id = "ma"

    def __init__(self, signal_type: SignalType) -> None:
        self.signal_type = signal_type

    def generate_signal(self, bars: Sequence[Bar]) -> Signal:
        return Signal(
            instrument=bars[-1].instrument,
            timestamp=bars[-1].timestamp,
            signal_type=self.signal_type,
            strategy_id=self.strategy_id,
        )


def make_repository(path) -> SQLitePaperRepository:
    repository = SQLitePaperRepository(path)
    repository.initialize()
    return repository


def make_broker(initial_cash: Decimal = Decimal("1000")) -> PaperBroker:
    ids = iter(("new-order-1", "new-order-2"))
    return PaperBroker(
        initial_cash=initial_cash,
        order_id_factory=lambda: next(ids),
        submitted_at_factory=lambda: T1,
    )


def make_order(
    order_id: str = "order-1",
    *,
    instrument: Instrument = BTC,
    side: OrderSide = OrderSide.BUY,
    quantity: Decimal = Decimal("2"),
    status: OrderStatus = OrderStatus.PENDING,
) -> Order:
    return Order(
        order_id=order_id,
        instrument=instrument,
        side=side,
        quantity=quantity,
        strategy_id="ma",
        submitted_at=T0,
        status=status,
    )


def make_fill(
    order: Order,
    *,
    fill_id: str = "fill-1",
    fill_price: Decimal = Decimal("100"),
    instrument: Instrument | None = None,
) -> ExecutionFill:
    return ExecutionFill(
        fill_id=fill_id,
        order_id=order.order_id,
        instrument=instrument or order.instrument,
        side=order.side,
        quantity=order.quantity,
        fill_price=fill_price,
        fee_amount=Decimal("0"),
        filled_at=T0,
        strategy_id=order.strategy_id,
    )


def persist_filled(
    repository: SQLitePaperRepository,
    *,
    order_id: str = "order-1",
    instrument: Instrument = BTC,
    side: OrderSide = OrderSide.BUY,
    quantity: Decimal = Decimal("2"),
    fill_id: str = "fill-1",
    fill_price: Decimal = Decimal("100"),
    timestamp: datetime = T0,
) -> tuple[Order, ExecutionFill]:
    pending = make_order(
        order_id,
        instrument=instrument,
        side=side,
        quantity=quantity,
    )
    filled = pending.transition_to(OrderStatus.FILLED)
    fill = make_fill(filled, fill_id=fill_id, fill_price=fill_price)
    repository.register_order_submission(
        PaperDecisionKey(
            PaperCursorScope(instrument, "ma", "day"), timestamp
        ),
        pending,
    )
    repository.save_execution(filled, fill)
    return filled, fill


def recover(repository, initial_cash: Decimal = Decimal("1000")) -> PaperBroker:
    return recover_paper_runtime(
        repository,
        SCOPE,
        initial_cash=initial_cash,
        order_id_factory=lambda: "future-order",
        submitted_at_factory=lambda: T1,
    ).broker


def make_bar(timestamp: datetime = T1) -> Bar:
    return Bar(
        instrument=BTC,
        interval="day",
        timestamp=timestamp,
        open=Decimal("110"),
        high=Decimal("110"),
        low=Decimal("110"),
        close=Decimal("110"),
        volume=Decimal("1"),
    )


def assert_issue(result, text: str) -> None:
    assert not result.is_safe_to_trade
    assert any(text in issue for issue in result.issues)


def test_empty_account_is_safe(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    result = reconcile_paper_runtime(make_broker(), repository, cursor_scope=SCOPE)

    assert result.is_safe_to_trade
    assert result.issues == ()


def test_normal_recovered_filled_order_and_multiple_executions_are_safe(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    persist_filled(repository)
    persist_filled(
        repository,
        order_id="eth-order",
        instrument=ETH,
        quantity=Decimal("1"),
        fill_id="eth-fill",
        fill_price=Decimal("50"),
        timestamp=T1,
    )
    repository.save_last_processed_bar_timestamp(SCOPE, T1)
    broker = recover(repository)

    result = reconcile_paper_runtime(broker, repository, cursor_scope=SCOPE)

    assert result.is_safe_to_trade
    assert broker.cash == Decimal("750")
    assert broker.position_quantity(BTC) == Decimal("2")
    assert broker.position_quantity(ETH) == Decimal("1")


def test_broker_only_and_repository_only_orders_are_unsafe(tmp_path) -> None:
    empty_repository = make_repository(tmp_path / "empty.db")
    broker = make_broker()
    broker.submit(
        OrderIntent(BTC, T1, "ma", OrderSide.BUY, Decimal("1"))
    )
    assert_issue(
        reconcile_paper_runtime(broker, empty_repository), "broker-only order"
    )

    repository = make_repository(tmp_path / "repository.db")
    repository.save_order(make_order(status=OrderStatus.CANCELED))
    assert_issue(
        reconcile_paper_runtime(make_broker(), repository),
        "repository-only order",
    )


def test_order_state_mismatch_is_unsafe(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    canceled = make_order(status=OrderStatus.CANCELED)
    repository.save_order(canceled)
    runtime_pending = make_order()
    broker = PaperBroker.from_persisted_state(
        initial_cash=Decimal("1000"),
        orders=[runtime_pending],
        fills=[],
        order_id_factory=lambda: "new-order",
        submitted_at_factory=lambda: T1,
    )

    assert_issue(
        reconcile_paper_runtime(broker, repository), "order content mismatch"
    )


def test_order_without_decision_mapping_is_unsafe(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    canceled = make_order(status=OrderStatus.CANCELED)
    repository.save_order(canceled)
    broker = PaperBroker.from_persisted_state(
        initial_cash=Decimal("1000"),
        orders=[canceled],
        fills=[],
        order_id_factory=lambda: "new-order",
        submitted_at_factory=lambda: T1,
    )

    assert_issue(
        reconcile_paper_runtime(broker, repository),
        "no durable decision mapping",
    )


def test_broker_only_repository_only_and_content_mismatched_fills_are_unsafe(
    tmp_path,
) -> None:
    repository = make_repository(tmp_path / "paper.db")
    durable_order, durable_fill = persist_filled(repository)

    assert_issue(
        reconcile_paper_runtime(make_broker(), repository),
        "repository-only fill",
    )

    runtime_fill = make_fill(durable_order, fill_price=Decimal("101"))
    mismatched_broker = PaperBroker.from_persisted_state(
        initial_cash=Decimal("1000"),
        orders=[durable_order],
        fills=[runtime_fill],
        order_id_factory=lambda: "new-order",
        submitted_at_factory=lambda: T1,
    )
    assert_issue(
        reconcile_paper_runtime(mismatched_broker, repository),
        "fill content mismatch",
    )

    empty_repository = make_repository(tmp_path / "empty.db")
    broker_only = PaperBroker.from_persisted_state(
        initial_cash=Decimal("1000"),
        orders=[durable_order],
        fills=[durable_fill],
        order_id_factory=lambda: "new-order",
        submitted_at_factory=lambda: T1,
    )
    assert_issue(
        reconcile_paper_runtime(broker_only, empty_repository),
        "broker-only fill",
    )


@pytest.mark.parametrize("status", [OrderStatus.CANCELED, OrderStatus.REJECTED])
def test_terminal_nonfilled_order_with_fill_is_unsafe(tmp_path, status) -> None:
    repository = make_repository(tmp_path / f"{status.value}.db")
    order = make_order(status=status)
    repository.save_order(order)
    repository.save_fill(make_fill(order))

    result = reconcile_paper_runtime(make_broker(), repository)

    assert_issue(result, "persisted fill requires a FILLED order")


def test_filled_order_without_fill_is_unsafe(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    repository.save_order(make_order(status=OrderStatus.FILLED))

    assert_issue(
        reconcile_paper_runtime(make_broker(), repository),
        "exactly one persisted fill",
    )


def test_cash_and_position_mismatch_are_unsafe(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    persist_filled(repository)
    cash_broker = recover(repository)
    cash_broker._cash += Decimal("1")
    assert_issue(
        reconcile_paper_runtime(cash_broker, repository), "cash mismatch"
    )

    position_broker = recover(repository)
    position_broker._positions[BTC] += Decimal("1")
    assert_issue(
        reconcile_paper_runtime(position_broker, repository),
        "position mismatch",
    )


def test_pending_crash_is_unsafe_and_gate_does_not_run_cycle(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    pending = make_order()
    repository.register_order_submission(PaperDecisionKey(SCOPE, T0), pending)
    broker = recover(repository)
    readiness = reconcile_paper_runtime(broker, repository)
    calls = 0

    def forbidden_operation():
        nonlocal calls
        calls += 1
        return "not reached"

    with pytest.raises(PaperTradingNotReadyError, match="PENDING"):
        run_when_paper_ready(readiness, forbidden_operation)

    assert not readiness.is_safe_to_trade
    assert calls == 0
    assert broker.list_fills() == ()
    assert broker.cash == Decimal("1000")


def test_corrupt_decision_target_is_unsafe(tmp_path) -> None:
    database = tmp_path / "paper.db"
    repository = make_repository(database)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            """
            INSERT INTO paper_order_decisions (
                venue, symbol, strategy_id, timeframe,
                closed_bar_timestamp, order_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("upbit", "KRW-BTC", "ma", "day", T0.isoformat(), "missing"),
        )

    assert_issue(
        reconcile_paper_runtime(make_broker(), repository),
        "decision references missing order",
    )


def test_corrupt_fill_missing_order_is_unsafe(tmp_path) -> None:
    database = tmp_path / "paper.db"
    repository = make_repository(database)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            """
            INSERT INTO paper_fills (
                fill_id, order_id, venue, symbol, side, quantity,
                fill_price, fee_amount, filled_at, strategy_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "fill-1",
                "missing",
                "upbit",
                "KRW-BTC",
                "buy",
                "1",
                "100",
                "0",
                T0.isoformat(),
                "ma",
            ),
        )

    assert_issue(
        reconcile_paper_runtime(make_broker(), repository),
        "persisted fill references missing order",
    )


def test_safe_restart_gate_allows_real_new_cycle(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    persist_filled(repository)
    broker = recover(repository)
    readiness = reconcile_paper_runtime(broker, repository)

    result = run_when_paper_ready(
        readiness,
        lambda: run_paper_cycle(
            [make_bar()],
            FixedStrategy(SignalType.BEARISH_CROSSOVER),
            broker,
            BasicRiskManager(),
            RiskLimits(Decimal("1000"), Decimal("1"), Decimal("0")),
            target_weight=Decimal("1"),
            quantity_step=Decimal("1"),
            min_trade_amount=Decimal("0"),
            execution_reference_price=Decimal("110"),
            fill_id_factory=lambda: "new-fill",
            clock=FixedClock(T1),
            repository=repository,
        ),
    )

    assert readiness.is_safe_to_trade
    assert result.fill is not None
    assert result.fill.side is OrderSide.SELL
    assert broker.position_quantity(BTC) == Decimal("0")
