from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from investing_plz.adapters.upbit_execution import UpbitExecutionAccountingUpdate
from investing_plz.adapters.upbit_order import UpbitTradeSnapshot


_ORDER_STATES = frozenset(("wait", "watch", "done", "cancel"))


class UpbitExecutionLedgerConflictError(ValueError):
    """A durable Upbit execution fact conflicts with an incoming update."""


@dataclass(frozen=True, slots=True)
class UpbitPersistedOrderAccountingState:
    order_id: str
    cumulative_paid_fee: Decimal
    executed_volume: Decimal
    remaining_volume: Decimal
    state: str
    trades_count: int

    def __post_init__(self) -> None:
        _require_order_id(self.order_id)
        for name in (
            "cumulative_paid_fee",
            "executed_volume",
            "remaining_volume",
        ):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be a Decimal")
            if not value.is_finite():
                raise ValueError(f"{name} must be finite")
            if value < 0:
                raise ValueError(f"{name} must not be negative")
        if self.state not in _ORDER_STATES:
            raise ValueError("state is not supported")
        if type(self.trades_count) is not int or self.trades_count < 0:
            raise ValueError("trades_count must be a non-negative int")


@dataclass(frozen=True, slots=True)
class UpbitExecutionLedgerApplyResult:
    inserted_trade_ids: tuple[str, ...]
    order_state_changed: bool


class UpbitExecutionLedger(Protocol):
    def initialize(self) -> None: ...

    def apply_update(
        self, update: UpbitExecutionAccountingUpdate
    ) -> UpbitExecutionLedgerApplyResult: ...

    def get_trade(self, trade_id: str) -> UpbitTradeSnapshot | None: ...

    def list_trades(
        self, order_id: str | None = None
    ) -> tuple[UpbitTradeSnapshot, ...]: ...

    def get_order_accounting_state(
        self, order_id: str
    ) -> UpbitPersistedOrderAccountingState | None: ...

    def list_order_accounting_states(
        self,
    ) -> tuple[UpbitPersistedOrderAccountingState, ...]: ...


def _require_order_id(order_id: object) -> str:
    if (
        not isinstance(order_id, str)
        or not order_id
        or order_id != order_id.strip()
    ):
        raise ValueError("order_id must be a non-empty unpadded string")
    return order_id
