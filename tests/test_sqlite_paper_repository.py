from datetime import datetime, timezone
from decimal import Decimal

import pytest

from investing_plz.broker import ExecutionFill
from investing_plz.domain import Instrument, Order, OrderSide, OrderStatus
from investing_plz.storage import (
    PaperCursorScope,
    PaperRepository,
    SQLitePaperRepository,
)


BTC = Instrument("upbit", "KRW-BTC")
ETH = Instrument("upbit", "KRW-ETH")
SUBMITTED_AT = datetime(2026, 9, 25, 1, tzinfo=timezone.utc)
FILLED_AT = datetime(2026, 9, 25, 1, 1, tzinfo=timezone.utc)


def make_order(
    order_id: str = "order-1",
    *,
    instrument: Instrument = BTC,
    side: OrderSide = OrderSide.BUY,
    quantity: Decimal = Decimal("0.01000000"),
    submitted_at: datetime = SUBMITTED_AT,
    status: OrderStatus = OrderStatus.PENDING,
) -> Order:
    return Order(
        order_id=order_id,
        instrument=instrument,
        side=side,
        quantity=quantity,
        strategy_id="moving_average_crossover",
        submitted_at=submitted_at,
        status=status,
    )


def make_fill(
    fill_id: str = "fill-1",
    *,
    order: Order | None = None,
    quantity: Decimal | None = None,
    fill_price: Decimal = Decimal("50000000.1250"),
    fee_amount: Decimal = Decimal("250.000125000"),
    filled_at: datetime = FILLED_AT,
) -> ExecutionFill:
    order = order or make_order()
    return ExecutionFill(
        fill_id=fill_id,
        order_id=order.order_id,
        instrument=order.instrument,
        side=order.side,
        quantity=quantity if quantity is not None else order.quantity,
        fill_price=fill_price,
        fee_amount=fee_amount,
        filled_at=filled_at,
        strategy_id=order.strategy_id,
    )


@pytest.fixture
def repository(tmp_path) -> SQLitePaperRepository:
    repository = SQLitePaperRepository(tmp_path / "paper.db")
    repository.initialize()
    return repository


def test_repository_satisfies_paper_repository_contract(repository) -> None:
    contract: PaperRepository = repository

    assert contract.list_orders() == ()
    assert contract.list_fills() == ()


@pytest.mark.parametrize("side", [OrderSide.BUY, OrderSide.SELL])
def test_order_round_trip_preserves_side_decimal_and_utc(repository, side) -> None:
    order = make_order(side=side, quantity=Decimal("1.2500"))

    repository.save_order(order)
    restored = repository.get_order(order.order_id)

    assert restored == order
    assert restored is not None
    assert str(restored.quantity) == "1.2500"
    assert restored.submitted_at == SUBMITTED_AT
    assert restored.submitted_at.tzinfo is timezone.utc


def test_order_status_update_replaces_pending_snapshot(repository) -> None:
    pending = make_order()
    filled = pending.transition_to(OrderStatus.FILLED)

    repository.save_order(pending)
    repository.save_order(filled)

    assert repository.get_order(pending.order_id) == filled
    assert repository.list_open_orders() == ()


@pytest.mark.parametrize("status", [OrderStatus.CANCELED, OrderStatus.REJECTED])
def test_terminal_order_status_round_trip(repository, status) -> None:
    order = make_order(status=status)

    repository.save_order(order)

    assert repository.get_order(order.order_id) == order


def test_missing_order_returns_none(repository) -> None:
    assert repository.get_order("missing") is None


def test_orders_for_multiple_instruments_are_independent_and_deterministic(
    repository,
) -> None:
    later_btc = make_order(
        "btc-order",
        submitted_at=datetime(2026, 9, 25, 2, tzinfo=timezone.utc),
    )
    earlier_eth = make_order(
        "eth-order",
        instrument=ETH,
        submitted_at=datetime(2026, 9, 25, 1, tzinfo=timezone.utc),
    )

    repository.save_order(later_btc)
    repository.save_order(earlier_eth)

    assert repository.list_orders() == (earlier_eth, later_btc)
    assert repository.list_open_orders() == (earlier_eth, later_btc)


def test_same_order_id_cannot_silently_replace_order_data(repository) -> None:
    repository.save_order(make_order())

    with pytest.raises(ValueError, match="different order data"):
        repository.save_order(make_order(quantity=Decimal("0.02")))

    assert repository.get_order("order-1") == make_order()


def test_fill_round_trip_preserves_decimal_utc_and_order_link(repository) -> None:
    order = make_order()
    fill = make_fill(order=order)
    repository.save_order(order)

    assert repository.save_fill(fill) is True
    restored = repository.get_fill(fill.fill_id)

    assert restored == fill
    assert restored is not None
    assert restored.order_id == order.order_id
    assert str(restored.quantity) == "0.01000000"
    assert str(restored.fill_price) == "50000000.1250"
    assert str(restored.fee_amount) == "250.000125000"
    assert restored.filled_at == FILLED_AT
    assert restored.filled_at.tzinfo is timezone.utc


def test_fill_duplicate_is_idempotent_only_for_identical_content(repository) -> None:
    order = make_order()
    fill = make_fill(order=order)
    repository.save_order(order)

    assert repository.save_fill(fill) is True
    assert repository.save_fill(fill) is False

    conflicting = make_fill(order=order, fill_price=Decimal("50000001"))
    with pytest.raises(ValueError, match="different fill data"):
        repository.save_fill(conflicting)

    assert repository.get_fill(fill.fill_id) == fill


def test_fill_requires_a_persisted_order(repository) -> None:
    with pytest.raises(ValueError, match="unknown order_id"):
        repository.save_fill(make_fill())

    assert repository.list_fills() == ()


def test_missing_fill_returns_none(repository) -> None:
    assert repository.get_fill("missing") is None


def test_fills_are_listed_in_deterministic_time_then_id_order(repository) -> None:
    order = make_order()
    repository.save_order(order)
    later = make_fill(
        "fill-z",
        order=order,
        filled_at=datetime(2026, 9, 25, 3, tzinfo=timezone.utc),
    )
    same_time_b = make_fill("fill-b", order=order, filled_at=FILLED_AT)
    same_time_a = make_fill("fill-a", order=order, filled_at=FILLED_AT)

    for fill in (later, same_time_b, same_time_a):
        repository.save_fill(fill)

    assert repository.list_fills() == (same_time_a, same_time_b, later)


def test_cursor_missing_save_update_and_scope_independence(repository) -> None:
    btc_day = PaperCursorScope(BTC, "ma", "day")
    eth_day = PaperCursorScope(ETH, "ma", "day")
    btc_minute = PaperCursorScope(BTC, "ma", "minute60")
    btc_other_strategy = PaperCursorScope(BTC, "other", "day")
    first = datetime(2026, 9, 24, tzinfo=timezone.utc)
    second = datetime(2026, 9, 25, tzinfo=timezone.utc)

    assert repository.get_last_processed_bar_timestamp(btc_day) is None
    repository.save_last_processed_bar_timestamp(btc_day, first)
    repository.save_last_processed_bar_timestamp(eth_day, second)
    repository.save_last_processed_bar_timestamp(btc_minute, second)
    repository.save_last_processed_bar_timestamp(btc_other_strategy, first)
    repository.save_last_processed_bar_timestamp(btc_day, second)

    assert repository.get_last_processed_bar_timestamp(btc_day) == second
    assert repository.get_last_processed_bar_timestamp(eth_day) == second
    assert repository.get_last_processed_bar_timestamp(btc_minute) == second
    assert repository.get_last_processed_bar_timestamp(btc_other_strategy) == first


def test_cursor_rejects_naive_timestamp_without_mutation(repository) -> None:
    scope = PaperCursorScope(BTC, "ma", "day")

    with pytest.raises(ValueError, match="timezone-aware"):
        repository.save_last_processed_bar_timestamp(
            scope, datetime(2026, 9, 25)
        )

    assert repository.get_last_processed_bar_timestamp(scope) is None


def test_repository_reopen_restores_order_fill_and_cursor(tmp_path) -> None:
    database = tmp_path / "paper-restart.db"
    repository_a = SQLitePaperRepository(database)
    repository_a.initialize()
    pending = make_order()
    filled = pending.transition_to(OrderStatus.FILLED)
    fill = make_fill(order=pending)
    scope = PaperCursorScope(BTC, pending.strategy_id, "day")
    cursor = datetime(2026, 9, 25, tzinfo=timezone.utc)

    repository_a.save_order(pending)
    repository_a.save_order(filled)
    repository_a.save_fill(fill)
    repository_a.save_last_processed_bar_timestamp(scope, cursor)

    repository_b = SQLitePaperRepository(database)
    repository_b.initialize()

    assert repository_b.get_order(filled.order_id) == filled
    assert repository_b.get_fill(fill.fill_id) == fill
    assert repository_b.get_last_processed_bar_timestamp(scope) == cursor
    assert repository_b.list_orders() == (filled,)
    assert repository_b.list_fills() == (fill,)
