from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from investing_plz.broker.models import ExecutionFill
from investing_plz.domain import Instrument, Order
from investing_plz.domain.time import require_utc


@dataclass(frozen=True, slots=True)
class PaperCursorScope:
    """Stable identity for one paper decision cursor."""

    instrument: Instrument
    strategy_id: str
    timeframe: str

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, Instrument):
            raise TypeError("instrument must be an Instrument")
        if not isinstance(self.strategy_id, str) or not self.strategy_id.strip():
            raise ValueError("strategy_id must not be empty")
        if not isinstance(self.timeframe, str) or not self.timeframe.strip():
            raise ValueError("timeframe must not be empty")


@dataclass(frozen=True, slots=True)
class PaperDecisionKey:
    """Identity of one strategy decision for one completed market bar."""

    scope: PaperCursorScope
    closed_bar_timestamp: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.scope, PaperCursorScope):
            raise TypeError("scope must be a PaperCursorScope")
        require_utc(self.closed_bar_timestamp)


@dataclass(frozen=True, slots=True)
class PaperOrderDecision:
    decision_key: PaperDecisionKey
    order_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.decision_key, PaperDecisionKey):
            raise TypeError("decision_key must be a PaperDecisionKey")
        if not isinstance(self.order_id, str) or not self.order_id.strip():
            raise ValueError("order_id must not be empty")


class PaperRepository(Protocol):
    """Persistence contract for paper orders, fills, and scheduler cursors."""

    def initialize(self) -> None: ...

    def save_order(self, order: Order) -> None: ...

    def get_order(self, order_id: str) -> Order | None: ...

    def list_orders(self) -> tuple[Order, ...]: ...

    def list_open_orders(self) -> tuple[Order, ...]: ...

    def register_order_submission(
        self, decision_key: PaperDecisionKey, order: Order
    ) -> bool: ...

    def get_order_for_decision(
        self, decision_key: PaperDecisionKey
    ) -> Order | None: ...

    def find_open_order_for_scope(
        self, scope: PaperCursorScope
    ) -> Order | None: ...

    def list_order_decisions(self) -> tuple[PaperOrderDecision, ...]: ...

    def save_fill(self, fill: ExecutionFill) -> bool: ...

    def get_fill(self, fill_id: str) -> ExecutionFill | None: ...

    def list_fills(self) -> tuple[ExecutionFill, ...]: ...

    def save_execution(
        self, order: Order, fill: ExecutionFill | None
    ) -> None: ...

    def get_last_processed_bar_timestamp(
        self, scope: PaperCursorScope
    ) -> datetime | None: ...

    def save_last_processed_bar_timestamp(
        self, scope: PaperCursorScope, timestamp: datetime
    ) -> None: ...
