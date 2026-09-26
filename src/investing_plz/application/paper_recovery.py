from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import logging

from investing_plz.broker import PaperBroker
from investing_plz.storage.paper import (
    PaperCursorScope,
    PaperRepository,
    PaperSessionConfig,
    PaperSessionConfigurationError,
)
from investing_plz.structured_logging import log_event


_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PaperRecoveryResult:
    broker: PaperBroker
    last_processed_bar_timestamp: datetime | None


def recover_paper_runtime(
    repository: PaperRepository,
    session_config: PaperSessionConfig,
    *,
    order_id_factory: Callable[[], str],
    submitted_at_factory: Callable[[], datetime],
) -> PaperRecoveryResult:
    """Rebuild paper account projection and cursor from durable records."""

    if not isinstance(session_config, PaperSessionConfig):
        raise TypeError("session_config must be a PaperSessionConfig")
    durable_configs = repository.list_session_configs()
    if len(durable_configs) > 1:
        raise PaperSessionConfigurationError(
            "Paper DB contains multiple session configurations"
        )
    if not durable_configs:
        if _has_any_durable_trading_state(repository):
            raise PaperSessionConfigurationError(
                "durable paper state exists without a session configuration"
            )
        repository.register_session_config(session_config)
        durable_config = session_config
    else:
        durable_config = durable_configs[0]
    if durable_config != session_config:
        raise PaperSessionConfigurationError(
            "requested paper session configuration does not match durable configuration"
        )

    _validate_durable_session_scope(repository, durable_config.scope)

    broker = PaperBroker.from_persisted_state(
        initial_cash=durable_config.initial_cash,
        orders=repository.list_orders(),
        fills=repository.list_fills(),
        fee_rate=durable_config.fee_rate,
        slippage_bps=durable_config.slippage_bps,
        order_id_factory=order_id_factory,
        submitted_at_factory=submitted_at_factory,
    )
    result = PaperRecoveryResult(
        broker=broker,
        last_processed_bar_timestamp=(
            repository.get_last_processed_bar_timestamp(durable_config.scope)
        ),
    )
    log_event(
        _LOGGER,
        "paper.runtime_recovered",
        instrument=str(durable_config.instrument),
        strategy_id=durable_config.strategy_id,
        timeframe=durable_config.timeframe,
        order_count=len(broker.list_orders()),
        fill_count=len(broker.list_fills()),
        bar_timestamp=(
            None
            if result.last_processed_bar_timestamp is None
            else result.last_processed_bar_timestamp.isoformat()
        ),
    )
    return result


def _has_any_durable_trading_state(repository: PaperRepository) -> bool:
    return bool(
        repository.list_orders()
        or repository.list_fills()
        or repository.list_order_decisions()
        or repository.list_cursor_scopes()
    )


def _validate_durable_session_scope(
    repository: PaperRepository, scope: PaperCursorScope
) -> None:
    for order in repository.list_orders():
        if order.instrument != scope.instrument or order.strategy_id != scope.strategy_id:
            raise PaperSessionConfigurationError(
                f"durable order is outside the Paper session scope: {order.order_id}"
            )
    for decision in repository.list_order_decisions():
        if decision.decision_key.scope != scope:
            raise PaperSessionConfigurationError(
                "durable decision is outside the Paper session scope"
            )
    for cursor_scope in repository.list_cursor_scopes():
        if cursor_scope != scope:
            raise PaperSessionConfigurationError(
                "durable cursor is outside the Paper session scope"
            )
