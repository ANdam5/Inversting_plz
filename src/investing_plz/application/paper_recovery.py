from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import logging

from investing_plz.broker import PaperBroker
from investing_plz.storage.paper import (
    PaperCursorScope,
    PaperRepository,
    PaperSessionConfig,
)
from investing_plz.structured_logging import log_event


_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PaperRecoveryResult:
    broker: PaperBroker
    last_processed_bar_timestamp: datetime | None


class PaperSessionConfigurationError(ValueError):
    pass


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
    durable_config = repository.get_session_config(session_config.scope)
    if durable_config is None:
        if _has_durable_state_for_scope(repository, session_config.scope):
            raise PaperSessionConfigurationError(
                "durable paper state exists without a session configuration"
            )
        repository.register_session_config(session_config)
        durable_config = session_config
    elif durable_config != session_config:
        raise PaperSessionConfigurationError(
            "requested paper session configuration does not match durable configuration"
        )

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


def _has_durable_state_for_scope(
    repository: PaperRepository, scope: PaperCursorScope
) -> bool:
    if repository.get_last_processed_bar_timestamp(scope) is not None:
        return True
    if any(
        decision.decision_key.scope == scope
        for decision in repository.list_order_decisions()
    ):
        return True
    if any(
        order.instrument == scope.instrument and order.strategy_id == scope.strategy_id
        for order in repository.list_orders()
    ):
        return True
    return any(
        fill.instrument == scope.instrument and fill.strategy_id == scope.strategy_id
        for fill in repository.list_fills()
    )
