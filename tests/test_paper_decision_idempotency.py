from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal

from investing_plz.application import run_paper_cycle
from investing_plz.broker import PaperBroker
from investing_plz.clock import FixedClock
from investing_plz.domain import Bar, Instrument, OrderIntent, OrderSide, OrderStatus
from investing_plz.risk import BasicRiskManager, RiskLimits
from investing_plz.storage import (
    PaperCursorScope,
    PaperDecisionKey,
    SQLitePaperRepository,
)
from investing_plz.strategy import Signal, SignalType


BTC = Instrument("upbit", "KRW-BTC")
ETH = Instrument("upbit", "KRW-ETH")
BAR_TIME = datetime(2026, 9, 25, tzinfo=timezone.utc)
CYCLE_TIME = datetime(2026, 9, 26, tzinfo=timezone.utc)


class BullishStrategy:
    def __init__(self, strategy_id: str = "ma") -> None:
        self.strategy_id = strategy_id

    def generate_signal(self, bars: Sequence[Bar]) -> Signal:
        return Signal(
            instrument=bars[-1].instrument,
            timestamp=bars[-1].timestamp,
            signal_type=SignalType.BULLISH_CROSSOVER,
            strategy_id=self.strategy_id,
        )


def make_bar(
    *,
    instrument: Instrument = BTC,
    interval: str = "day",
    timestamp: datetime = BAR_TIME,
) -> Bar:
    return Bar(
        instrument=instrument,
        interval=interval,
        timestamp=timestamp,
        open=Decimal("100"),
        high=Decimal("100"),
        low=Decimal("100"),
        close=Decimal("100"),
        volume=Decimal("1"),
    )


def make_broker(
    order_ids: list[str],
    *,
    initial_cash: Decimal = Decimal("1000"),
    fee_rate: Decimal = Decimal("0"),
) -> PaperBroker:
    return PaperBroker(
        initial_cash=initial_cash,
        fee_rate=fee_rate,
        order_id_factory=lambda: order_ids.pop(0),
        submitted_at_factory=lambda: CYCLE_TIME,
    )


def run_cycle(
    repository: SQLitePaperRepository,
    broker: PaperBroker,
    *,
    bar: Bar | None = None,
    strategy_id: str = "ma",
    max_order_amount: Decimal = Decimal("1000"),
    fill_ids: list[str] | None = None,
):
    fill_ids = fill_ids if fill_ids is not None else ["fill-1"]
    return run_paper_cycle(
        [bar or make_bar()],
        BullishStrategy(strategy_id),
        broker,
        BasicRiskManager(),
        RiskLimits(max_order_amount, Decimal("1"), Decimal("0")),
        target_weight=Decimal("1"),
        quantity_step=Decimal("1"),
        min_trade_amount=Decimal("0"),
        execution_reference_price=Decimal("100"),
        fill_id_factory=lambda: fill_ids.pop(0),
        clock=FixedClock(CYCLE_TIME),
        repository=repository,
    )


def make_repository(path) -> SQLitePaperRepository:
    repository = SQLitePaperRepository(path)
    repository.initialize()
    return repository


def test_same_filled_decision_blocks_resubmit_and_does_not_consume_ids(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    first_order_ids = ["order-1"]
    first_fill_ids = ["fill-1"]
    first_broker = make_broker(first_order_ids)

    first = run_cycle(
        repository,
        first_broker,
        max_order_amount=Decimal("300"),
        fill_ids=first_fill_ids,
    )
    retry_order_ids = ["order-unused"]
    retry_fill_ids = ["fill-unused"]
    retry_broker = make_broker(retry_order_ids)
    retry = run_cycle(
        repository,
        retry_broker,
        max_order_amount=Decimal("300"),
        fill_ids=retry_fill_ids,
    )

    assert first.order is not None and first.order.status is OrderStatus.FILLED
    assert first.fill is not None
    assert retry.order == first.order
    assert retry.fill is None
    assert retry_order_ids == ["order-unused"]
    assert retry_fill_ids == ["fill-unused"]
    assert repository.list_orders() == (first.order,)
    assert repository.list_fills() == (first.fill,)


def test_broker_rejected_decision_is_persisted_and_blocks_retry(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    broker = make_broker(["order-1"], fee_rate=Decimal("0.10"))

    first = run_cycle(repository, broker, fill_ids=["fill-1"])
    retry_order_ids = ["order-unused"]
    retry_fill_ids = ["fill-unused"]
    retry = run_cycle(
        repository,
        make_broker(retry_order_ids, fee_rate=Decimal("0.10")),
        fill_ids=retry_fill_ids,
    )

    assert first.order is not None and first.order.status is OrderStatus.REJECTED
    assert first.fill is None
    assert repository.get_order(first.order.order_id) == first.order
    assert repository.list_fills() == ()
    assert retry.order == first.order
    assert retry.fill is None
    assert retry_order_ids == ["order-unused"]
    assert retry_fill_ids == ["fill-unused"]


def test_pending_order_blocks_a_newer_decision_for_same_scope(tmp_path) -> None:
    repository = make_repository(tmp_path / "paper.db")
    pending = make_broker(["pending-order"]).submit(
        OrderIntent(BTC, CYCLE_TIME, "ma", OrderSide.BUY, Decimal("1"))
    )
    old_key = PaperDecisionKey(
        PaperCursorScope(BTC, "ma", "day"),
        BAR_TIME,
    )
    repository.register_order_submission(old_key, pending)
    newer_bar = make_bar(timestamp=datetime(2026, 9, 26, tzinfo=timezone.utc))
    order_ids = ["order-unused"]
    fill_ids = ["fill-unused"]

    result = run_cycle(
        repository,
        make_broker(order_ids),
        bar=newer_bar,
        fill_ids=fill_ids,
    )

    assert result.order == pending
    assert result.fill is None
    assert order_ids == ["order-unused"]
    assert fill_ids == ["fill-unused"]


def test_pending_protection_is_independent_across_scope_dimensions(tmp_path) -> None:
    cases = (
        (make_bar(instrument=ETH), "ma"),
        (make_bar(), "other"),
        (make_bar(interval="minute60"), "ma"),
    )
    for index, (bar, strategy_id) in enumerate(cases):
        repository = make_repository(tmp_path / f"paper-{index}.db")
        pending = make_broker([f"pending-{index}"]).submit(
            OrderIntent(BTC, CYCLE_TIME, "ma", OrderSide.BUY, Decimal("1"))
        )
        repository.register_order_submission(
            PaperDecisionKey(PaperCursorScope(BTC, "ma", "day"), BAR_TIME),
            pending,
        )

        result = run_cycle(
            repository,
            make_broker([f"new-order-{index}"]),
            bar=bar,
            strategy_id=strategy_id,
            fill_ids=[f"new-fill-{index}"],
        )

        assert result.order is not None
        assert result.order.order_id == f"new-order-{index}"
        assert result.order.status is OrderStatus.FILLED
        assert result.fill is not None


def test_repository_reopen_without_cursor_still_blocks_same_decision(tmp_path) -> None:
    database = tmp_path / "paper.db"
    repository_a = make_repository(database)
    first = run_cycle(
        repository_a,
        make_broker(["order-1"]),
        max_order_amount=Decimal("300"),
        fill_ids=["fill-1"],
    )
    assert first.order is not None
    assert first.fill is not None

    repository_b = make_repository(database)
    scope = PaperCursorScope(BTC, "ma", "day")
    assert repository_b.get_last_processed_bar_timestamp(scope) is None
    order_ids = ["order-unused"]
    fill_ids = ["fill-unused"]

    retry = run_cycle(
        repository_b,
        make_broker(order_ids),
        max_order_amount=Decimal("300"),
        fill_ids=fill_ids,
    )

    assert retry.order == first.order
    assert retry.fill is None
    assert order_ids == ["order-unused"]
    assert fill_ids == ["fill-unused"]
    assert repository_b.list_orders() == (first.order,)
    assert repository_b.list_fills() == (first.fill,)
