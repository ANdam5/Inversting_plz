from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import logging
import time
from typing import Protocol

from investing_plz.application.paper_cycle import run_paper_cycle
from investing_plz.application.paper_reconciliation import (
    PaperTradingNotReadyError,
    reconcile_paper_runtime,
)
from investing_plz.application.paper_recovery import recover_paper_runtime
from investing_plz.application.paper_safety import (
    ManualKillSwitch,
    evaluate_paper_safety,
)
from investing_plz.application.paper_scheduler import (
    PaperPollingScheduler,
    PaperPollResult,
)
from investing_plz.clock import Clock
from investing_plz.domain import Bar, Instrument
from investing_plz.market_data import is_closed_bar
from investing_plz.market_data.errors import MarketDataProviderError
from investing_plz.risk import BasicRiskManager, RiskLimits
from investing_plz.storage import PaperRepository, PaperSessionConfig
from investing_plz.strategy import MovingAverageCrossoverStrategy
from investing_plz.structured_logging import log_event


_LOGGER = logging.getLogger(__name__)


class PaperPublicMarketData(Protocol):
    def get_bars(
        self,
        instrument: Instrument,
        interval: str,
        *,
        since=None,
    ) -> Sequence[Bar]: ...

    def get_current_price(self, instrument: Instrument) -> Decimal: ...


@dataclass(frozen=True, slots=True)
class PaperRuntimeResult:
    poll_result: PaperPollResult | None
    cash: Decimal
    position_quantity: Decimal
    last_processed_bar_timestamp: datetime | None
    reconciliation_safe: bool
    trading_enabled: bool
    session_created: bool


def run_paper_runtime(
    session_config: PaperSessionConfig,
    *,
    repository: PaperRepository,
    market_data: PaperPublicMarketData,
    clock: Clock,
    poll_interval: timedelta,
    max_data_delay: timedelta,
    trading_enabled: bool,
    once: bool,
    order_id_factory: Callable[[], str],
    fill_id_factory: Callable[[], str],
    correlation_id_factory: Callable[[], str],
    submitted_at_factory: Callable[[], datetime],
    sleeper: Callable[[float], None] = time.sleep,
    loop_sleep_seconds: float = 0.25,
) -> PaperRuntimeResult:
    """Compose and run the provider-neutral Paper runtime."""

    if poll_interval <= timedelta(0):
        raise ValueError("poll_interval must be greater than zero")
    if max_data_delay < timedelta(0):
        raise ValueError("max_data_delay must not be negative")
    if loop_sleep_seconds <= 0:
        raise ValueError("loop_sleep_seconds must be greater than zero")

    log_event(
        _LOGGER,
        "paper.runtime_starting",
        instrument=str(session_config.instrument),
        strategy_id=session_config.strategy_id,
        timeframe=session_config.timeframe,
    )
    repository.initialize()
    session_created = repository.get_session_config(session_config.scope) is None
    recovery = recover_paper_runtime(
        repository,
        session_config,
        order_id_factory=order_id_factory,
        submitted_at_factory=submitted_at_factory,
    )
    log_event(
        _LOGGER,
        "paper.configuration_registered" if session_created else "paper.configuration_loaded",
        instrument=str(session_config.instrument),
        strategy_id=session_config.strategy_id,
        timeframe=session_config.timeframe,
    )
    readiness = reconcile_paper_runtime(
        recovery.broker, repository, cursor_scope=session_config.scope
    )
    if not readiness.is_safe_to_trade:
        log_event(_LOGGER, "paper.runtime_startup_blocked", issues=readiness.issues)
        raise PaperTradingNotReadyError("; ".join(readiness.issues))

    kill_switch = ManualKillSwitch(trading_enabled=trading_enabled)
    log_event(
        _LOGGER,
        "paper.trading_enabled" if trading_enabled else "paper.trading_disabled",
    )
    strategy = MovingAverageCrossoverStrategy(
        fast_window=session_config.fast_window,
        slow_window=session_config.slow_window,
    )
    if session_config.strategy_id != strategy.strategy_id:
        raise ValueError(
            f"unsupported paper strategy_id: {session_config.strategy_id}"
        )
    risk_limits = RiskLimits(
        session_config.max_order_amount,
        session_config.max_instrument_weight,
        session_config.min_cash_reserve,
    )

    def closed_bars_provider() -> tuple[Bar, ...]:
        now = clock.now()
        bars = market_data.get_bars(
            session_config.instrument, session_config.timeframe
        )
        closed = tuple(bar for bar in bars if is_closed_bar(bar, now=now))
        return closed[-strategy.minimum_bars :]

    def cycle_runner(bars, reference_price):
        return run_paper_cycle(
            bars,
            strategy,
            recovery.broker,
            BasicRiskManager(),
            risk_limits,
            target_weight=session_config.target_weight,
            quantity_step=session_config.quantity_step,
            min_trade_amount=session_config.min_trade_amount,
            execution_reference_price=reference_price,
            fee_rate=session_config.fee_rate,
            slippage_bps=session_config.slippage_bps,
            fill_id_factory=fill_id_factory,
            clock=clock,
            repository=repository,
        )

    scheduler = PaperPollingScheduler(
        clock=clock,
        poll_interval=poll_interval,
        closed_bars_provider=closed_bars_provider,
        execution_price_provider=lambda: market_data.get_current_price(
            session_config.instrument
        ),
        cycle_runner=cycle_runner,
        initial_last_processed_bar_timestamp=(
            recovery.last_processed_bar_timestamp
        ),
        cursor_saver=lambda timestamp: (
            repository.save_last_processed_bar_timestamp(
                session_config.scope, timestamp
            )
        ),
        safety_evaluator=lambda bar, now: evaluate_paper_safety(
            bar,
            now=now,
            max_data_delay=max_data_delay,
            kill_switch=kill_switch,
            reconciliation=readiness,
        ),
        correlation_id_factory=correlation_id_factory,
    )

    poll_result: PaperPollResult | None = None
    try:
        if once:
            poll_result = scheduler.run_if_due()
        else:
            while True:
                try:
                    poll_result = scheduler.run_if_due()
                except MarketDataProviderError as error:
                    log_event(
                        _LOGGER,
                        "paper.market_data_failed",
                        reason=str(error),
                    )
                sleeper(loop_sleep_seconds)
    except KeyboardInterrupt:
        pass
    finally:
        log_event(_LOGGER, "paper.runtime_stopped")

    return PaperRuntimeResult(
        poll_result=poll_result,
        cash=recovery.broker.cash,
        position_quantity=recovery.broker.position_quantity(
            session_config.instrument
        ),
        last_processed_bar_timestamp=scheduler.last_processed_bar_timestamp,
        reconciliation_safe=readiness.is_safe_to_trade,
        trading_enabled=kill_switch.is_trading_enabled,
        session_created=session_created,
    )
