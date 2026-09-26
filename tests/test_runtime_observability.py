import logging
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from investing_plz.application import (
    ManualKillSwitch,
    PaperPollingScheduler,
    PaperReconciliationResult,
    evaluate_paper_safety,
    new_paper_correlation_id,
    new_paper_fill_id,
    new_paper_order_id,
    reconcile_paper_runtime,
    run_paper_cycle,
)
from investing_plz.broker import PaperBroker
from investing_plz.clock import FixedClock
from investing_plz.domain import Bar, Instrument, OrderIntent, OrderSide
from investing_plz.risk import BasicRiskManager, RiskLimits
from investing_plz.storage import SQLitePaperRepository
from investing_plz.strategy import Signal, SignalType
from investing_plz.structured_logging import correlation_context


INSTRUMENT = Instrument("upbit", "KRW-BTC")
BAR_TIME = datetime(2026, 9, 25, tzinfo=timezone.utc)
CYCLE_TIME = BAR_TIME + timedelta(days=1)


class BullishStrategy:
    strategy_id = "ma"

    def generate_signal(self, bars):
        return Signal(
            instrument=bars[-1].instrument,
            timestamp=bars[-1].timestamp,
            signal_type=SignalType.BULLISH_CROSSOVER,
            strategy_id=self.strategy_id,
        )


def make_bar() -> Bar:
    return Bar(
        instrument=INSTRUMENT,
        interval="day",
        timestamp=BAR_TIME,
        open=Decimal("100"),
        high=Decimal("100"),
        low=Decimal("100"),
        close=Decimal("100"),
        volume=Decimal("1"),
    )


def make_broker(*, order_id_factory) -> PaperBroker:
    return PaperBroker(
        initial_cash=Decimal("1000"),
        order_id_factory=order_id_factory,
        submitted_at_factory=lambda: CYCLE_TIME,
    )


def test_production_runtime_ids_have_distinct_prefixes_and_uuid_format() -> None:
    generated = (
        new_paper_order_id(),
        new_paper_fill_id(),
        new_paper_correlation_id(),
    )

    assert len(set(generated)) == 3
    for value, prefix in zip(
        generated,
        ("paper-order", "paper-fill", "paper-correlation"),
        strict=True,
    ):
        assert re.fullmatch(
            rf"{prefix}-[0-9a-f]{{8}}-[0-9a-f]{{4}}-4[0-9a-f]{{3}}-"
            r"[89ab][0-9a-f]{3}-[0-9a-f]{12}",
            value,
        )


def test_production_ids_do_not_collide_across_repository_restart(tmp_path) -> None:
    database = tmp_path / "paper.db"
    repository_a = SQLitePaperRepository(database)
    repository_a.initialize()
    broker_a = make_broker(order_id_factory=new_paper_order_id)
    order_a = broker_a.submit(
        OrderIntent(INSTRUMENT, CYCLE_TIME, "ma", OrderSide.BUY, Decimal("1"))
    )
    fill_a = broker_a.execute_order(
        order_a.order_id,
        reference_price=Decimal("100"),
        fill_id=new_paper_fill_id(),
        filled_at=CYCLE_TIME,
    )
    assert fill_a is not None
    filled_a = broker_a.get_order(order_a.order_id)
    assert filled_a is not None
    repository_a.save_order(order_a)
    repository_a.save_execution(filled_a, fill_a)

    repository_b = SQLitePaperRepository(database)
    repository_b.initialize()
    broker_b = make_broker(order_id_factory=new_paper_order_id)
    order_b = broker_b.submit(
        OrderIntent(INSTRUMENT, CYCLE_TIME, "ma", OrderSide.BUY, Decimal("1"))
    )
    fill_b = broker_b.execute_order(
        order_b.order_id,
        reference_price=Decimal("100"),
        fill_id=new_paper_fill_id(),
        filled_at=CYCLE_TIME,
    )
    assert fill_b is not None
    filled_b = broker_b.get_order(order_b.order_id)
    assert filled_b is not None
    repository_b.save_order(order_b)
    repository_b.save_execution(filled_b, fill_b)

    assert order_a.order_id != order_b.order_id
    assert fill_a.fill_id != fill_b.fill_id
    assert len(repository_b.list_orders()) == 2
    assert len(repository_b.list_fills()) == 2


def test_scheduler_cycle_order_and_fill_logs_share_correlation(caplog) -> None:
    broker = make_broker(order_id_factory=lambda: "order-1")
    clock = FixedClock(CYCLE_TIME)

    def cycle_runner(bars, price):
        return run_paper_cycle(
            bars,
            BullishStrategy(),
            broker,
            BasicRiskManager(),
            RiskLimits(Decimal("1000"), Decimal("1"), Decimal("0")),
            target_weight=Decimal("0.5"),
            quantity_step=Decimal("1"),
            min_trade_amount=Decimal("0"),
            execution_reference_price=price,
            fill_id_factory=lambda: "fill-1",
            clock=clock,
        )

    scheduler = PaperPollingScheduler(
        clock=clock,
        poll_interval=timedelta(minutes=1),
        closed_bars_provider=lambda: [make_bar()],
        execution_price_provider=lambda: Decimal("100"),
        cycle_runner=cycle_runner,
        correlation_id_factory=lambda: "correlation-1",
    )

    with caplog.at_level(logging.INFO):
        result = scheduler.run_if_due()

    assert result.processed
    assert result.cycle_result is not None
    assert result.cycle_result.fill is not None
    records = {
        record.event: record
        for record in caplog.records
        if hasattr(record, "event")
    }
    for event in (
        "paper.cycle_started",
        "paper.order_submitted",
        "paper.order_filled",
        "paper.cycle_completed",
    ):
        assert records[event].correlation_id == "correlation-1"
    assert records["paper.order_submitted"].order_id == "order-1"
    assert records["paper.order_filled"].order_id == "order-1"
    assert records["paper.order_filled"].fill_id == "fill-1"


def test_no_bar_does_not_consume_correlation_id() -> None:
    correlation_ids = ["correlation-unused"]
    scheduler = PaperPollingScheduler(
        clock=FixedClock(CYCLE_TIME),
        poll_interval=timedelta(minutes=1),
        closed_bars_provider=lambda: [],
        execution_price_provider=lambda: Decimal("100"),
        cycle_runner=lambda bars, price: None,
        correlation_id_factory=lambda: correlation_ids.pop(0),
    )

    result = scheduler.run_if_due()

    assert not result.processed
    assert correlation_ids == ["correlation-unused"]


def test_duplicate_decision_log_blocks_new_order_and_preserves_correlation(
    caplog, tmp_path
) -> None:
    repository = SQLitePaperRepository(tmp_path / "paper.db")
    repository.initialize()
    first = run_paper_cycle(
        [make_bar()],
        BullishStrategy(),
        make_broker(order_id_factory=lambda: "order-1"),
        BasicRiskManager(),
        RiskLimits(Decimal("1000"), Decimal("1"), Decimal("0")),
        target_weight=Decimal("0.5"),
        quantity_step=Decimal("1"),
        min_trade_amount=Decimal("0"),
        execution_reference_price=Decimal("100"),
        fill_id_factory=lambda: "fill-1",
        clock=FixedClock(CYCLE_TIME),
        repository=repository,
    )
    unused_order_ids = ["order-unused"]
    unused_fill_ids = ["fill-unused"]

    with caplog.at_level(logging.INFO), correlation_context("correlation-duplicate"):
        duplicate = run_paper_cycle(
            [make_bar()],
            BullishStrategy(),
            make_broker(order_id_factory=lambda: unused_order_ids.pop(0)),
            BasicRiskManager(),
            RiskLimits(Decimal("1000"), Decimal("1"), Decimal("0")),
            target_weight=Decimal("0.5"),
            quantity_step=Decimal("1"),
            min_trade_amount=Decimal("0"),
            execution_reference_price=Decimal("100"),
            fill_id_factory=lambda: unused_fill_ids.pop(0),
            clock=FixedClock(CYCLE_TIME),
            repository=repository,
        )

    record = next(
        record
        for record in caplog.records
        if getattr(record, "event", None) == "paper.duplicate_decision_blocked"
    )
    assert duplicate.order == first.order
    assert duplicate.fill is None
    assert unused_order_ids == ["order-unused"]
    assert unused_fill_ids == ["fill-unused"]
    assert record.correlation_id == "correlation-duplicate"
    assert record.order_id == "order-1"


def test_safety_block_log_has_correlation_and_issues(caplog) -> None:
    scheduler = PaperPollingScheduler(
        clock=FixedClock(CYCLE_TIME),
        poll_interval=timedelta(minutes=1),
        closed_bars_provider=lambda: [make_bar()],
        execution_price_provider=lambda: (_ for _ in ()).throw(
            AssertionError("price must not be read")
        ),
        cycle_runner=lambda bars, price: (_ for _ in ()).throw(
            AssertionError("cycle must not run")
        ),
        safety_evaluator=lambda bar, now: evaluate_paper_safety(
            bar,
            now=now,
            max_data_delay=timedelta(0),
            kill_switch=ManualKillSwitch(),
            reconciliation=PaperReconciliationResult(()),
        ),
        correlation_id_factory=lambda: "correlation-blocked",
    )

    with caplog.at_level(logging.INFO):
        result = scheduler.run_if_due()

    record = next(
        record
        for record in caplog.records
        if getattr(record, "event", None) == "paper.safety_blocked"
    )
    assert not result.processed
    assert record.correlation_id == "correlation-blocked"
    assert "manual kill switch is disabled" in record.issues


def test_reconciliation_unsafe_log_exposes_issue(caplog, tmp_path) -> None:
    repository = SQLitePaperRepository(tmp_path / "paper.db")
    repository.initialize()
    broker = make_broker(order_id_factory=lambda: "order-1")
    broker.submit(
        OrderIntent(INSTRUMENT, CYCLE_TIME, "ma", OrderSide.BUY, Decimal("1"))
    )

    with caplog.at_level(logging.INFO), correlation_context("correlation-reconcile"):
        result = reconcile_paper_runtime(broker, repository)

    record = next(
        record
        for record in caplog.records
        if getattr(record, "event", None) == "paper.reconciliation_unsafe"
    )
    assert not result.is_safe_to_trade
    assert record.correlation_id == "correlation-reconcile"
    assert any("broker-only order" in issue for issue in record.issues)
