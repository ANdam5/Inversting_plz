from dataclasses import dataclass
from typing import Protocol

from investing_plz.adapters.upbit_order import (
    UpbitOrderSnapshot,
    UpbitTradeSnapshot,
)


_TERMINAL_STATES = frozenset(("done", "cancel"))


class UpbitOrderProgressError(ValueError):
    """Successive Upbit order snapshots do not form valid forward progress."""


class UpbitOrderStatusSource(Protocol):
    def get_order(self, order_id: str) -> UpbitOrderSnapshot: ...


@dataclass(frozen=True, slots=True)
class UpbitOrderProgress:
    previous: UpbitOrderSnapshot | None
    current: UpbitOrderSnapshot
    newly_observed_trades: tuple[UpbitTradeSnapshot, ...]
    status_changed: bool
    became_terminal: bool


def compare_upbit_order_progress(
    previous: UpbitOrderSnapshot,
    current: UpbitOrderSnapshot,
) -> UpbitOrderProgress:
    if not isinstance(previous, UpbitOrderSnapshot) or not isinstance(
        current, UpbitOrderSnapshot
    ):
        raise TypeError("previous and current must be UpbitOrderSnapshot values")

    identity_fields = ("uuid", "market", "side", "order_type", "created_at")
    if any(getattr(previous, name) != getattr(current, name) for name in identity_fields):
        raise UpbitOrderProgressError("order identity changed between snapshots")
    if current.executed_volume < previous.executed_volume:
        raise UpbitOrderProgressError("executed_volume must not decrease")
    if current.trades_count < previous.trades_count:
        raise UpbitOrderProgressError("trades_count must not decrease")
    if current.paid_fee < previous.paid_fee:
        raise UpbitOrderProgressError("paid_fee must not decrease")
    if previous.state in _TERMINAL_STATES and current.state not in _TERMINAL_STATES:
        raise UpbitOrderProgressError("terminal order must not become non-terminal")

    previous_trades = {trade.trade_id: trade for trade in previous.trades}
    for trade in current.trades:
        observed = previous_trades.get(trade.trade_id)
        if observed is not None and observed != trade:
            raise UpbitOrderProgressError("observed trade content changed")
    new_trades = tuple(
        trade for trade in current.trades if trade.trade_id not in previous_trades
    )
    status_changed = current.state != previous.state
    return UpbitOrderProgress(
        previous=previous,
        current=current,
        newly_observed_trades=new_trades,
        status_changed=status_changed,
        became_terminal=(
            previous.state not in _TERMINAL_STATES
            and current.state in _TERMINAL_STATES
        ),
    )


class UpbitOrderTracker:
    """Poll one injected status source and emit each observed trade at most once."""

    def __init__(self, order_id: str, source: UpbitOrderStatusSource) -> None:
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("order_id must not be empty")
        self._order_id = order_id
        self._source = source
        self._current: UpbitOrderSnapshot | None = None
        self._observed_trade_ids: set[str] = set()

    @property
    def current(self) -> UpbitOrderSnapshot | None:
        return self._current

    @property
    def is_terminal(self) -> bool:
        return self._current is not None and self._current.state in _TERMINAL_STATES

    def poll(self) -> UpbitOrderProgress:
        current = self._source.get_order(self._order_id)
        if not isinstance(current, UpbitOrderSnapshot):
            raise TypeError("status source must return an UpbitOrderSnapshot")
        if current.uuid != self._order_id:
            raise UpbitOrderProgressError(
                "status source returned a snapshot for a different requested order"
            )

        previous = self._current
        if previous is None:
            candidate_trades = current.trades
            progress = UpbitOrderProgress(
                previous=None,
                current=current,
                newly_observed_trades=candidate_trades,
                status_changed=False,
                became_terminal=current.state in _TERMINAL_STATES,
            )
        else:
            progress = compare_upbit_order_progress(previous, current)
            candidate_trades = progress.newly_observed_trades

        new_trades = tuple(
            trade
            for trade in candidate_trades
            if trade.trade_id not in self._observed_trade_ids
        )
        if new_trades != progress.newly_observed_trades:
            progress = UpbitOrderProgress(
                previous=progress.previous,
                current=progress.current,
                newly_observed_trades=new_trades,
                status_changed=progress.status_changed,
                became_terminal=progress.became_terminal,
            )

        self._observed_trade_ids.update(trade.trade_id for trade in current.trades)
        self._current = current
        return progress
