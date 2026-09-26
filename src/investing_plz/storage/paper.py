from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from investing_plz.broker.models import ExecutionFill
from investing_plz.domain import Instrument, Order


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


class PaperRepository(Protocol):
    """Persistence contract for paper orders, fills, and scheduler cursors."""

    def initialize(self) -> None: ...

    def save_order(self, order: Order) -> None: ...

    def get_order(self, order_id: str) -> Order | None: ...

    def list_orders(self) -> tuple[Order, ...]: ...

    def list_open_orders(self) -> tuple[Order, ...]: ...

    def save_fill(self, fill: ExecutionFill) -> bool: ...

    def get_fill(self, fill_id: str) -> ExecutionFill | None: ...

    def list_fills(self) -> tuple[ExecutionFill, ...]: ...

    def get_last_processed_bar_timestamp(
        self, scope: PaperCursorScope
    ) -> datetime | None: ...

    def save_last_processed_bar_timestamp(
        self, scope: PaperCursorScope, timestamp: datetime
    ) -> None: ...
