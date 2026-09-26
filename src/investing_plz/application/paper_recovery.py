from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from investing_plz.broker import PaperBroker
from investing_plz.storage.paper import PaperCursorScope, PaperRepository


@dataclass(frozen=True, slots=True)
class PaperRecoveryResult:
    broker: PaperBroker
    last_processed_bar_timestamp: datetime | None


def recover_paper_runtime(
    repository: PaperRepository,
    scope: PaperCursorScope,
    *,
    initial_cash: Decimal,
    fee_rate: Decimal = Decimal("0"),
    slippage_bps: Decimal = Decimal("0"),
    order_id_factory: Callable[[], str],
    submitted_at_factory: Callable[[], datetime],
) -> PaperRecoveryResult:
    """Rebuild paper account projection and cursor from durable records."""

    broker = PaperBroker.from_persisted_state(
        initial_cash=initial_cash,
        orders=repository.list_orders(),
        fills=repository.list_fills(),
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
        order_id_factory=order_id_factory,
        submitted_at_factory=submitted_at_factory,
    )
    return PaperRecoveryResult(
        broker=broker,
        last_processed_bar_timestamp=(
            repository.get_last_processed_bar_timestamp(scope)
        ),
    )
