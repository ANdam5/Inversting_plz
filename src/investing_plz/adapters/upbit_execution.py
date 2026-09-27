from dataclasses import dataclass
from decimal import Decimal

from investing_plz.adapters.upbit_order import UpbitTradeSnapshot
from investing_plz.adapters.upbit_order_tracker import UpbitOrderProgress


_ORDER_STATES = frozenset(("wait", "watch", "done", "cancel"))


@dataclass(frozen=True, slots=True)
class UpbitExecutionAccountingUpdate:
    """Exact REST accounting facts newly observed for one Upbit order.

    Trade rows deliberately carry no inferred fee. The order-level cumulative
    paid fee remains the recovery source of truth; a future WebSocket feed may
    enrich trade details, but accounting correctness must not depend on it.
    """

    order_id: str
    newly_observed_trades: tuple[UpbitTradeSnapshot, ...]
    cumulative_paid_fee: Decimal
    current_state: str
    current_executed_volume: Decimal
    current_remaining_volume: Decimal
    current_trades_count: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.order_id, str)
            or not self.order_id
            or self.order_id != self.order_id.strip()
        ):
            raise ValueError("order_id must be a non-empty unpadded string")
        if not isinstance(self.newly_observed_trades, tuple) or not all(
            isinstance(trade, UpbitTradeSnapshot)
            for trade in self.newly_observed_trades
        ):
            raise TypeError(
                "newly_observed_trades must be a tuple of UpbitTradeSnapshot"
            )
        trade_ids = [trade.trade_id for trade in self.newly_observed_trades]
        if len(trade_ids) != len(set(trade_ids)):
            raise ValueError("newly_observed_trades contains duplicate trade ids")

        for name in (
            "cumulative_paid_fee",
            "current_executed_volume",
            "current_remaining_volume",
        ):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be a Decimal")
            if not value.is_finite():
                raise ValueError(f"{name} must be finite")
            if value < 0:
                raise ValueError(f"{name} must not be negative")

        if self.current_state not in _ORDER_STATES:
            raise ValueError("current_state is not supported")
        if type(self.current_trades_count) is not int or self.current_trades_count < 0:
            raise ValueError("current_trades_count must be a non-negative int")

    @property
    def executed_quantity_delta(self) -> Decimal:
        return sum(
            (trade.volume for trade in self.newly_observed_trades), Decimal("0")
        )

    @property
    def executed_notional_delta(self) -> Decimal:
        return sum(
            (trade.funds for trade in self.newly_observed_trades), Decimal("0")
        )

    @property
    def weighted_average_price(self) -> Decimal | None:
        quantity = self.executed_quantity_delta
        if quantity == 0:
            return None
        return self.executed_notional_delta / quantity


def upbit_order_progress_to_accounting_update(
    progress: UpbitOrderProgress,
) -> UpbitExecutionAccountingUpdate:
    """Project observed order progress into exact, persistable accounting facts."""

    if not isinstance(progress, UpbitOrderProgress):
        raise TypeError("progress must be an UpbitOrderProgress")
    current = progress.current
    current_trades = {trade.trade_id: trade for trade in current.trades}
    for trade in progress.newly_observed_trades:
        if current_trades.get(trade.trade_id) != trade:
            raise ValueError("newly observed trade is not present in current snapshot")

    return UpbitExecutionAccountingUpdate(
        order_id=current.uuid,
        newly_observed_trades=progress.newly_observed_trades,
        cumulative_paid_fee=current.paid_fee,
        current_state=current.state,
        current_executed_volume=current.executed_volume,
        current_remaining_volume=current.remaining_volume,
        current_trades_count=current.trades_count,
    )
