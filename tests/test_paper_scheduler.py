from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from investing_plz.application import (
    PaperCycleResult,
    PaperPollingScheduler,
    run_paper_cycle,
)
from investing_plz.broker import PaperBroker
from investing_plz.domain import Bar, Instrument, OrderIntent, OrderSide
from investing_plz.risk import (
    BasicRiskManager,
    RiskDecision,
    RiskLimits,
    RiskStatus,
)
from investing_plz.strategy import Signal, SignalType


INSTRUMENT = Instrument("upbit", "KRW-BTC")
START = datetime(2026, 9, 26, tzinfo=timezone.utc)


@dataclass
class MutableClock:
    current: datetime

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


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


def make_bar(day: int, *, close: Decimal = Decimal("90")) -> Bar:
    return Bar(
        instrument=INSTRUMENT,
        interval="day",
        timestamp=datetime(2026, 9, day, tzinfo=timezone.utc),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=Decimal("1"),
    )


def neutral_result(bar: Bar) -> PaperCycleResult:
    return PaperCycleResult(
        signal=Signal(
            instrument=bar.instrument,
            timestamp=bar.timestamp,
            signal_type=SignalType.NEUTRAL,
            strategy_id="fixed_signal_strategy",
        ),
        order_intent=None,
        risk_decision=None,
        order=None,
        fill=None,
    )


def make_scheduler(
    *,
    clock: MutableClock,
    bars_provider,
    price_provider,
    cycle_runner,
    interval: timedelta = timedelta(minutes=1),
    cursor_saver=None,
) -> PaperPollingScheduler:
    return PaperPollingScheduler(
        clock=clock,
        poll_interval=interval,
        closed_bars_provider=bars_provider,
        execution_price_provider=price_provider,
        cycle_runner=cycle_runner,
        cursor_saver=cursor_saver,
    )


def test_first_call_polls_immediately_and_interval_blocks_early_repoll() -> None:
    clock = MutableClock(START)
    bar = make_bar(25)
    provider_calls = 0
    cycle_calls = 0

    def bars_provider():
        nonlocal provider_calls
        provider_calls += 1
        return [bar]

    def cycle_runner(bars, price):
        nonlocal cycle_calls
        cycle_calls += 1
        return neutral_result(bars[-1])

    scheduler = make_scheduler(
        clock=clock,
        bars_provider=bars_provider,
        price_provider=lambda: Decimal("100"),
        cycle_runner=cycle_runner,
    )

    first = scheduler.run_if_due()
    early = scheduler.run_if_due()
    clock.advance(timedelta(minutes=1))
    due_again = scheduler.run_if_due()

    assert first.poll_due and first.market_data_polled and first.processed
    assert not early.poll_due and not early.market_data_polled
    assert due_again.poll_due and due_again.market_data_polled
    assert not due_again.processed
    assert provider_calls == 2
    assert cycle_calls == 1


def test_empty_bars_skip_price_and_cycle_without_advancing_cursor() -> None:
    clock = MutableClock(START)
    price_calls = 0
    cycle_calls = 0

    def price_provider():
        nonlocal price_calls
        price_calls += 1
        return Decimal("100")

    def cycle_runner(bars, price):
        nonlocal cycle_calls
        cycle_calls += 1
        raise AssertionError("cycle must not run")

    scheduler = make_scheduler(
        clock=clock,
        bars_provider=lambda: [],
        price_provider=price_provider,
        cycle_runner=cycle_runner,
    )

    result = scheduler.run_if_due()

    assert result.poll_due and result.market_data_polled
    assert not result.processed
    assert result.newest_bar_timestamp is None
    assert scheduler.last_processed_bar_timestamp is None
    assert price_calls == 0
    assert cycle_calls == 0


def test_same_or_older_bar_is_not_processed_or_priced_again() -> None:
    clock = MutableClock(START)
    latest = make_bar(25)
    returned_bars = [[latest], [latest], [make_bar(24)]]
    price_calls = 0
    cycle_calls = 0

    def price_provider():
        nonlocal price_calls
        price_calls += 1
        return Decimal("100")

    def cycle_runner(bars, price):
        nonlocal cycle_calls
        cycle_calls += 1
        return neutral_result(bars[-1])

    scheduler = make_scheduler(
        clock=clock,
        bars_provider=lambda: returned_bars.pop(0),
        price_provider=price_provider,
        cycle_runner=cycle_runner,
    )

    assert scheduler.run_if_due().processed
    for _ in range(2):
        clock.advance(timedelta(minutes=1))
        assert not scheduler.run_if_due().processed

    assert scheduler.last_processed_bar_timestamp == latest.timestamp
    assert price_calls == 1
    assert cycle_calls == 1


def test_newer_bar_runs_one_more_cycle_and_uses_explicit_price() -> None:
    clock = MutableClock(START)
    first = make_bar(24, close=Decimal("80"))
    second = make_bar(25, close=Decimal("90"))
    histories = [[first], [first, second]]
    seen: list[tuple[datetime, Decimal]] = []

    def cycle_runner(bars, price):
        seen.append((bars[-1].timestamp, price))
        return neutral_result(bars[-1])

    scheduler = make_scheduler(
        clock=clock,
        bars_provider=lambda: histories.pop(0),
        price_provider=lambda: Decimal("123"),
        cycle_runner=cycle_runner,
    )

    assert scheduler.run_if_due().processed
    clock.advance(timedelta(minutes=1))
    second_result = scheduler.run_if_due()

    assert second_result.processed
    assert scheduler.last_processed_bar_timestamp == second.timestamp
    assert seen == [(first.timestamp, Decimal("123")), (second.timestamp, Decimal("123"))]
    assert Decimal("123") != second.close


def test_multiple_new_bars_trigger_one_latest_state_cycle_not_replay() -> None:
    clock = MutableClock(START)
    bars = [make_bar(23), make_bar(24), make_bar(25)]
    calls: list[tuple[int, datetime]] = []

    def cycle_runner(history, price):
        calls.append((len(history), history[-1].timestamp))
        return neutral_result(history[-1])

    scheduler = make_scheduler(
        clock=clock,
        bars_provider=lambda: bars,
        price_provider=lambda: Decimal("100"),
        cycle_runner=cycle_runner,
    )

    result = scheduler.run_if_due()

    assert result.processed
    assert calls == [(3, bars[-1].timestamp)]
    assert scheduler.last_processed_bar_timestamp == bars[-1].timestamp


@pytest.mark.parametrize("result_kind", ["neutral", "risk_rejected", "broker_rejected"])
def test_normal_cycle_results_advance_cursor(result_kind: str) -> None:
    clock = MutableClock(START)
    bar = make_bar(25)
    intent = OrderIntent(
        instrument=INSTRUMENT,
        timestamp=START,
        strategy_id="fixed_signal_strategy",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
    )
    signal = Signal(
        instrument=INSTRUMENT,
        timestamp=bar.timestamp,
        signal_type=SignalType.NEUTRAL,
        strategy_id="fixed_signal_strategy",
    )
    if result_kind == "risk_rejected":
        decision = RiskDecision(RiskStatus.REJECTED, intent, None, "test rejection")
        cycle_result = PaperCycleResult(signal, intent, decision, None, None)
    elif result_kind == "broker_rejected":
        broker = PaperBroker(
            initial_cash=Decimal("0"),
            order_id_factory=lambda: "order-1",
            submitted_at_factory=lambda: START,
        )
        order = broker.submit(intent)
        broker.execute_order(
            order.order_id,
            reference_price=Decimal("100"),
            fill_id="fill-1",
            filled_at=START,
        )
        cycle_result = PaperCycleResult(
            signal,
            intent,
            RiskDecision(RiskStatus.APPROVED, intent, intent, "approved"),
            broker.get_order(order.order_id),
            None,
        )
    else:
        cycle_result = neutral_result(bar)

    saved: list[datetime] = []
    scheduler = make_scheduler(
        clock=clock,
        bars_provider=lambda: [bar],
        price_provider=lambda: Decimal("100"),
        cycle_runner=lambda bars, price: cycle_result,
        cursor_saver=saved.append,
    )

    result = scheduler.run_if_due()

    assert result.processed
    assert result.cycle_result == cycle_result
    assert scheduler.last_processed_bar_timestamp == bar.timestamp
    assert saved == [bar.timestamp]


def test_cycle_exception_keeps_cursor_and_allows_next_due_retry() -> None:
    clock = MutableClock(START)
    bar = make_bar(25)
    attempts = 0
    saved: list[datetime] = []

    def cycle_runner(bars, price):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("cycle failed")
        return neutral_result(bars[-1])

    scheduler = make_scheduler(
        clock=clock,
        bars_provider=lambda: [bar],
        price_provider=lambda: Decimal("100"),
        cycle_runner=cycle_runner,
        cursor_saver=saved.append,
    )

    with pytest.raises(RuntimeError, match="cycle failed"):
        scheduler.run_if_due()
    assert scheduler.last_processed_bar_timestamp is None
    assert saved == []

    assert not scheduler.run_if_due().poll_due
    clock.advance(timedelta(minutes=1))
    retry = scheduler.run_if_due()

    assert retry.processed
    assert attempts == 2
    assert scheduler.last_processed_bar_timestamp == bar.timestamp
    assert saved == [bar.timestamp]


def test_cursor_save_failure_keeps_memory_cursor_and_retries_same_bar() -> None:
    clock = MutableClock(START)
    bar = make_bar(25)
    cycle_calls = 0
    save_attempts = 0

    def cycle_runner(bars, price):
        nonlocal cycle_calls
        cycle_calls += 1
        return neutral_result(bars[-1])

    def cursor_saver(timestamp):
        nonlocal save_attempts
        save_attempts += 1
        if save_attempts == 1:
            raise RuntimeError("cursor storage unavailable")

    scheduler = make_scheduler(
        clock=clock,
        bars_provider=lambda: [bar],
        price_provider=lambda: Decimal("100"),
        cycle_runner=cycle_runner,
        cursor_saver=cursor_saver,
    )

    with pytest.raises(RuntimeError, match="cursor storage unavailable"):
        scheduler.run_if_due()
    assert scheduler.last_processed_bar_timestamp is None

    clock.advance(timedelta(minutes=1))
    retry = scheduler.run_if_due()

    assert retry.processed
    assert scheduler.last_processed_bar_timestamp == bar.timestamp
    assert cycle_calls == 2
    assert save_attempts == 2


def test_scheduler_can_delegate_to_actual_run_paper_cycle() -> None:
    clock = MutableClock(START)
    bar = make_bar(25)
    broker = PaperBroker(
        initial_cash=Decimal("1000"),
        order_id_factory=lambda: "order-1",
        submitted_at_factory=lambda: START,
    )

    def cycle_runner(bars, price):
        return run_paper_cycle(
            bars,
            FixedSignalStrategy(SignalType.BULLISH_CROSSOVER),
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

    scheduler = make_scheduler(
        clock=clock,
        bars_provider=lambda: [bar],
        price_provider=lambda: Decimal("100"),
        cycle_runner=cycle_runner,
    )

    result = scheduler.run_if_due()

    assert result.processed
    assert result.cycle_result is not None
    assert result.cycle_result.fill is not None
    assert broker.position_quantity(INSTRUMENT) == Decimal("5")


def test_poll_interval_must_be_positive() -> None:
    for interval in (timedelta(0), timedelta(seconds=-1)):
        with pytest.raises(ValueError, match="greater than zero"):
            make_scheduler(
                clock=MutableClock(START),
                bars_provider=lambda: [],
                price_provider=lambda: Decimal("100"),
                cycle_runner=lambda bars, price: neutral_result(make_bar(25)),
                interval=interval,
            )
