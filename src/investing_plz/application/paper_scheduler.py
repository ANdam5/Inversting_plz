from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from investing_plz.application.paper_cycle import PaperCycleResult
from investing_plz.application.paper_safety import PaperSafetyResult
from investing_plz.clock import Clock
from investing_plz.domain import Bar
from investing_plz.domain.time import require_utc


ClosedBarsProvider = Callable[[], Sequence[Bar]]
ExecutionPriceProvider = Callable[[], Decimal]
PaperCycleRunner = Callable[[Sequence[Bar], Decimal], PaperCycleResult]
CursorSaver = Callable[[datetime], None]
SafetyEvaluator = Callable[[Bar | None, datetime], PaperSafetyResult]


@dataclass(frozen=True, slots=True)
class PaperPollResult:
    poll_due: bool
    market_data_polled: bool
    newest_bar_timestamp: datetime | None
    processed: bool
    cycle_result: PaperCycleResult | None
    safety_result: PaperSafetyResult | None = None


class PaperPollingScheduler:
    """Step-based in-memory poll cadence and new-closed-bar gate."""

    def __init__(
        self,
        *,
        clock: Clock,
        poll_interval: timedelta,
        closed_bars_provider: ClosedBarsProvider,
        execution_price_provider: ExecutionPriceProvider,
        cycle_runner: PaperCycleRunner,
        initial_last_processed_bar_timestamp: datetime | None = None,
        cursor_saver: CursorSaver | None = None,
        safety_evaluator: SafetyEvaluator | None = None,
    ) -> None:
        if poll_interval <= timedelta(0):
            raise ValueError("poll_interval must be greater than zero")
        self._clock = clock
        self._poll_interval = poll_interval
        self._closed_bars_provider = closed_bars_provider
        self._execution_price_provider = execution_price_provider
        self._cycle_runner = cycle_runner
        self._cursor_saver = cursor_saver
        self._safety_evaluator = safety_evaluator
        self._next_poll_at: datetime | None = None
        self._last_processed_bar_timestamp = (
            None
            if initial_last_processed_bar_timestamp is None
            else require_utc(initial_last_processed_bar_timestamp)
        )

    @property
    def last_processed_bar_timestamp(self) -> datetime | None:
        return self._last_processed_bar_timestamp

    def run_if_due(self) -> PaperPollResult:
        now = require_utc(self._clock.now())
        if self._next_poll_at is not None and now < self._next_poll_at:
            return PaperPollResult(False, False, None, False, None)

        bars = tuple(self._closed_bars_provider())
        self._next_poll_at = now + self._poll_interval
        if not bars:
            safety_result = (
                None
                if self._safety_evaluator is None
                else self._safety_evaluator(None, now)
            )
            return PaperPollResult(
                True, True, None, False, None, safety_result
            )

        timestamps = [bar.timestamp for bar in bars]
        if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
            raise ValueError("closed bars must have unique timestamps in ascending order")
        newest_timestamp = timestamps[-1]
        if (
            self._last_processed_bar_timestamp is not None
            and newest_timestamp <= self._last_processed_bar_timestamp
        ):
            return PaperPollResult(True, True, newest_timestamp, False, None)

        safety_result = (
            None
            if self._safety_evaluator is None
            else self._safety_evaluator(bars[-1], now)
        )
        if safety_result is not None and not safety_result.is_safe_to_trade:
            return PaperPollResult(
                True,
                True,
                newest_timestamp,
                False,
                None,
                safety_result,
            )

        reference_price = self._execution_price_provider()
        cycle_result = self._cycle_runner(bars, reference_price)
        if self._cursor_saver is not None:
            self._cursor_saver(newest_timestamp)
        self._last_processed_bar_timestamp = newest_timestamp
        return PaperPollResult(
            True,
            True,
            newest_timestamp,
            True,
            cycle_result,
            safety_result,
        )
