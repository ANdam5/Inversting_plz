from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from investing_plz.application import (
    ManualKillSwitch,
    PaperCycleResult,
    PaperPollingScheduler,
    PaperReconciliationResult,
    evaluate_paper_safety,
    run_paper_cycle,
)
from investing_plz.broker import PaperBroker
from investing_plz.domain import Bar, Instrument
from investing_plz.risk import BasicRiskManager, RiskLimits
from investing_plz.strategy import Signal, SignalType


INSTRUMENT = Instrument("upbit", "KRW-BTC")
BAR_OPEN = datetime(2026, 9, 25, tzinfo=timezone.utc)
BAR_COMPLETION = BAR_OPEN + timedelta(days=1)


@dataclass
class MutableClock:
    current: datetime

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


class BullishStrategy:
    strategy_id = "safety-strategy"

    def generate_signal(self, bars):
        bar = bars[-1]
        return Signal(
            instrument=bar.instrument,
            timestamp=bar.timestamp,
            signal_type=SignalType.BULLISH_CROSSOVER,
            strategy_id=self.strategy_id,
        )


def make_bar(timestamp: datetime = BAR_OPEN, *, interval: str = "day") -> Bar:
    return Bar(
        instrument=INSTRUMENT,
        interval=interval,
        timestamp=timestamp,
        open=Decimal("90"),
        high=Decimal("100"),
        low=Decimal("80"),
        close=Decimal("95"),
        volume=Decimal("1"),
    )


def neutral_result(bar: Bar) -> PaperCycleResult:
    return PaperCycleResult(
        signal=Signal(
            instrument=bar.instrument,
            timestamp=bar.timestamp,
            signal_type=SignalType.NEUTRAL,
            strategy_id="safety-strategy",
        ),
        order_intent=None,
        risk_decision=None,
        order=None,
        fill=None,
    )


def safe_reconciliation() -> PaperReconciliationResult:
    return PaperReconciliationResult(())


def evaluator(kill_switch, reconciliation, *, delay=timedelta(hours=1)):
    return lambda bar, now: evaluate_paper_safety(
        bar,
        now=now,
        max_data_delay=delay,
        kill_switch=kill_switch,
        reconciliation=reconciliation,
    )


def test_manual_kill_switch_defaults_disabled_and_can_toggle() -> None:
    switch = ManualKillSwitch()

    assert not switch.is_trading_enabled
    switch.enable()
    assert switch.is_trading_enabled
    switch.disable()
    assert not switch.is_trading_enabled


def test_freshness_uses_daily_completion_and_boundary_is_fresh() -> None:
    switch = ManualKillSwitch(trading_enabled=True)
    delay = timedelta(hours=1)

    before_boundary = evaluate_paper_safety(
        make_bar(),
        now=BAR_COMPLETION + timedelta(minutes=30),
        max_data_delay=delay,
        kill_switch=switch,
        reconciliation=safe_reconciliation(),
    )
    at_boundary = evaluate_paper_safety(
        make_bar(),
        now=BAR_COMPLETION + delay,
        max_data_delay=delay,
        kill_switch=switch,
        reconciliation=safe_reconciliation(),
    )

    assert before_boundary.is_safe_to_trade
    assert at_boundary.is_safe_to_trade


def test_stale_future_no_data_and_unsupported_timeframe_are_blocked() -> None:
    switch = ManualKillSwitch(trading_enabled=True)
    reconciliation = safe_reconciliation()

    stale = evaluate_paper_safety(
        make_bar(),
        now=BAR_COMPLETION + timedelta(hours=1, microseconds=1),
        max_data_delay=timedelta(hours=1),
        kill_switch=switch,
        reconciliation=reconciliation,
    )
    future = evaluate_paper_safety(
        make_bar(),
        now=BAR_COMPLETION - timedelta(microseconds=1),
        max_data_delay=timedelta(hours=1),
        kill_switch=switch,
        reconciliation=reconciliation,
    )
    no_data = evaluate_paper_safety(
        None,
        now=BAR_COMPLETION,
        max_data_delay=timedelta(hours=1),
        kill_switch=switch,
        reconciliation=reconciliation,
    )
    unsupported = evaluate_paper_safety(
        make_bar(interval="minute60"),
        now=BAR_COMPLETION,
        max_data_delay=timedelta(hours=1),
        kill_switch=switch,
        reconciliation=reconciliation,
    )

    assert not stale.is_safe_to_trade and "stale market data" in stale.issues[0]
    assert not future.is_safe_to_trade and "future" in future.issues[0]
    assert not no_data.is_safe_to_trade and "no closed" in no_data.issues[0]
    assert not unsupported.is_safe_to_trade and "unsupported" in unsupported.issues[0]


def test_delay_validation_and_zero_delay_completion_boundary() -> None:
    switch = ManualKillSwitch(trading_enabled=True)
    result = evaluate_paper_safety(
        make_bar(),
        now=BAR_COMPLETION,
        max_data_delay=timedelta(0),
        kill_switch=switch,
        reconciliation=safe_reconciliation(),
    )

    assert result.is_safe_to_trade
    with pytest.raises(ValueError, match="must not be negative"):
        evaluate_paper_safety(
            make_bar(),
            now=BAR_COMPLETION,
            max_data_delay=timedelta(microseconds=-1),
            kill_switch=switch,
            reconciliation=safe_reconciliation(),
        )


@pytest.mark.parametrize(
    ("enabled", "reconciliation", "now", "safe"),
    [
        (True, PaperReconciliationResult(()), BAR_COMPLETION, True),
        (True, PaperReconciliationResult(("cash mismatch",)), BAR_COMPLETION, False),
        (True, PaperReconciliationResult(()), BAR_COMPLETION + timedelta(hours=2), False),
        (False, PaperReconciliationResult(()), BAR_COMPLETION, False),
        (
            False,
            PaperReconciliationResult(("cash mismatch",)),
            BAR_COMPLETION + timedelta(hours=2),
            False,
        ),
    ],
)
def test_combined_safety_requires_reconciliation_freshness_and_enabled_switch(
    enabled, reconciliation, now, safe
) -> None:
    result = evaluate_paper_safety(
        make_bar(),
        now=now,
        max_data_delay=timedelta(hours=1),
        kill_switch=ManualKillSwitch(trading_enabled=enabled),
        reconciliation=reconciliation,
    )

    assert result.is_safe_to_trade is safe
    if not enabled and reconciliation.issues and now > BAR_COMPLETION + timedelta(hours=1):
        assert len(result.issues) == 3


def test_scheduler_blocks_stale_before_price_cycle_and_cursor() -> None:
    clock = MutableClock(BAR_COMPLETION + timedelta(hours=2))
    price_calls = 0
    cycle_calls = 0
    saved = []

    def price_provider():
        nonlocal price_calls
        price_calls += 1
        return Decimal("100")

    def cycle_runner(bars, price):
        nonlocal cycle_calls
        cycle_calls += 1
        return neutral_result(bars[-1])

    scheduler = PaperPollingScheduler(
        clock=clock,
        poll_interval=timedelta(minutes=1),
        closed_bars_provider=lambda: [make_bar()],
        execution_price_provider=price_provider,
        cycle_runner=cycle_runner,
        cursor_saver=saved.append,
        safety_evaluator=evaluator(
            ManualKillSwitch(trading_enabled=True), safe_reconciliation()
        ),
    )

    result = scheduler.run_if_due()

    assert not result.processed
    assert result.safety_result is not None
    assert not result.safety_result.is_safe_to_trade
    assert price_calls == cycle_calls == 0
    assert saved == []
    assert scheduler.last_processed_bar_timestamp is None


def test_kill_switch_reenable_processes_same_latest_bar_without_replay() -> None:
    clock = MutableClock(BAR_COMPLETION)
    switch = ManualKillSwitch()
    bars = [make_bar(BAR_OPEN), make_bar(BAR_OPEN + timedelta(days=1))]
    histories = [[bars[0]], bars, bars]
    seen = []
    scheduler = PaperPollingScheduler(
        clock=clock,
        poll_interval=timedelta(minutes=1),
        closed_bars_provider=lambda: histories.pop(0),
        execution_price_provider=lambda: Decimal("123"),
        cycle_runner=lambda history, price: (
            seen.append(history[-1].timestamp) or neutral_result(history[-1])
        ),
        safety_evaluator=evaluator(switch, safe_reconciliation()),
    )

    assert not scheduler.run_if_due().processed
    clock.advance(timedelta(days=1, minutes=1))
    assert not scheduler.run_if_due().processed
    switch.enable()
    clock.advance(timedelta(minutes=1))
    result = scheduler.run_if_due()

    assert result.processed
    assert seen == [bars[-1].timestamp]
    assert scheduler.last_processed_bar_timestamp == bars[-1].timestamp


def test_reconciliation_guard_blocks_actual_cycle_without_account_mutation() -> None:
    clock = MutableClock(BAR_COMPLETION)
    broker = PaperBroker(
        initial_cash=Decimal("1000"),
        order_id_factory=lambda: "order-1",
        submitted_at_factory=clock.now,
    )

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
        safety_evaluator=evaluator(
            ManualKillSwitch(trading_enabled=True),
            PaperReconciliationResult(("cash mismatch",)),
        ),
    )

    result = scheduler.run_if_due()

    assert not result.processed
    assert broker.cash == Decimal("1000")
    assert broker.position_quantity(INSTRUMENT) == 0
    assert broker.list_orders() == ()
    assert broker.list_fills() == ()
    assert scheduler.last_processed_bar_timestamp is None
