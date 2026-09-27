from collections.abc import Sequence
from decimal import Decimal

import pytest

from investing_plz.adapters.upbit_order import (
    UpbitOrderValidationError,
    upbit_order_response_to_snapshot,
    upbit_order_snapshot_to_order,
)
from investing_plz.adapters.upbit_order_tracker import (
    UpbitOrderProgressError,
    UpbitOrderTracker,
    compare_upbit_order_progress,
)
from investing_plz.domain import OrderStatus


def trade(trade_id: str, volume: str, *, minute: int) -> dict[str, object]:
    return {
        "market": "KRW-BTC",
        "uuid": trade_id,
        "price": "100",
        "volume": volume,
        "funds": str(Decimal(volume) * Decimal("100")),
        "side": "bid",
        "created_at": f"2026-09-27T00:{minute:02d}:00Z",
    }


def snapshot(
    *,
    state: str = "wait",
    executed: str = "0",
    remaining: str = "1",
    paid_fee: str = "0",
    trades: Sequence[dict[str, object]] = (),
    **overrides: object,
):
    payload: dict[str, object] = {
        "uuid": "order-1",
        "side": "bid",
        "ord_type": "limit",
        "price": "100",
        "state": state,
        "market": "KRW-BTC",
        "created_at": "2026-09-27T00:00:00Z",
        "volume": "1",
        "remaining_volume": remaining,
        "reserved_fee": "0.05",
        "remaining_fee": "0.05",
        "paid_fee": paid_fee,
        "locked": "100.05",
        "executed_volume": executed,
        "trades_count": len(trades),
        "trades": list(trades),
    }
    payload.update(overrides)
    return upbit_order_response_to_snapshot(payload)


class SequenceStatusSource:
    def __init__(self, snapshots) -> None:
        self._snapshots = iter(snapshots)
        self.calls: list[str] = []

    def get_order(self, order_id: str):
        self.calls.append(order_id)
        return next(self._snapshots)


def test_tracker_reports_each_partial_trade_once_until_done() -> None:
    trade_a = trade("trade-a", "0.4", minute=1)
    trade_b = trade("trade-b", "0.3", minute=2)
    trade_c = trade("trade-c", "0.3", minute=3)
    source = SequenceStatusSource(
        [
            snapshot(),
            snapshot(executed="0.4", remaining="0.6", trades=[trade_a]),
            snapshot(
                executed="0.7", remaining="0.3", trades=[trade_a, trade_b]
            ),
            snapshot(
                state="done",
                executed="1.0",
                remaining="0",
                trades=[trade_a, trade_b, trade_c],
            ),
        ]
    )
    tracker = UpbitOrderTracker("order-1", source)

    progresses = [tracker.poll() for _ in range(4)]

    assert [
        tuple(item.trade_id for item in progress.newly_observed_trades)
        for progress in progresses
    ] == [(), ("trade-a",), ("trade-b",), ("trade-c",)]
    assert progresses[-1].became_terminal
    assert tracker.is_terminal
    assert source.calls == ["order-1"] * 4


def test_identical_snapshot_does_not_repeat_trade() -> None:
    partial = snapshot(
        executed="0.4", remaining="0.6", trades=[trade("trade-a", "0.4", minute=1)]
    )
    tracker = UpbitOrderTracker("order-1", SequenceStatusSource([partial, partial]))

    first = tracker.poll()
    second = tracker.poll()

    assert tuple(item.trade_id for item in first.newly_observed_trades) == ("trade-a",)
    assert second.newly_observed_trades == ()
    assert not second.status_changed


def test_partial_then_cancel_preserves_trade_and_projects_canceled_order() -> None:
    partial_trade = trade("trade-a", "0.4", minute=1)
    partial = snapshot(
        executed="0.4", remaining="0.6", trades=[partial_trade]
    )
    canceled = snapshot(
        state="cancel",
        executed="0.4",
        remaining="0.6",
        trades=[partial_trade],
    )

    progress = compare_upbit_order_progress(partial, canceled)
    order = upbit_order_snapshot_to_order(
        progress.current, strategy_id="moving_average_crossover"
    )

    assert order.status is OrderStatus.CANCELED
    assert progress.current.trades[0].trade_id == "trade-a"
    assert progress.became_terminal


def test_partial_and_done_project_to_pending_and_filled() -> None:
    partial_trade = trade("trade-a", "0.4", minute=1)
    partial = snapshot(
        executed="0.4", remaining="0.6", trades=[partial_trade]
    )
    done = snapshot(
        state="done",
        executed="1",
        remaining="0",
        trades=[partial_trade, trade("trade-b", "0.6", minute=2)],
    )

    assert upbit_order_snapshot_to_order(
        partial, strategy_id="moving_average_crossover"
    ).status is OrderStatus.PENDING
    assert upbit_order_snapshot_to_order(
        done, strategy_id="moving_average_crossover"
    ).status is OrderStatus.FILLED


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("uuid", "other-order"),
        ("market", "KRW-ETH"),
        ("side", "ask"),
        ("ord_type", "market"),
        ("created_at", "2026-09-27T00:01:00Z"),
    ],
)
def test_progress_rejects_order_identity_changes(field: str, value: object) -> None:
    current_overrides: dict[str, object] = {field: value}
    if field == "side":
        current_overrides.update({"price": None, "ord_type": "market", "volume": "1"})
    elif field == "ord_type":
        current_overrides.update({"side": "ask", "price": None, "volume": "1"})

    with pytest.raises(UpbitOrderProgressError, match="identity"):
        compare_upbit_order_progress(snapshot(), snapshot(**current_overrides))


@pytest.mark.parametrize(
    ("previous_kwargs", "current_kwargs", "message"),
    [
        ({"executed": "0.4"}, {"executed": "0.3"}, "executed_volume"),
        (
            {"trades": [trade("trade-a", "0.4", minute=1)]},
            {"trades": []},
            "trades_count",
        ),
        ({"paid_fee": "0.04"}, {"paid_fee": "0.03"}, "paid_fee"),
        ({"state": "done"}, {"state": "wait"}, "terminal"),
    ],
)
def test_progress_rejects_cumulative_or_terminal_regression(
    previous_kwargs: dict[str, object],
    current_kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(UpbitOrderProgressError, match=message):
        compare_upbit_order_progress(
            snapshot(**previous_kwargs), snapshot(**current_kwargs)
        )


def test_tracker_rejects_source_snapshot_for_another_order() -> None:
    tracker = UpbitOrderTracker(
        "order-1", SequenceStatusSource([snapshot(uuid="order-2")])
    )

    with pytest.raises(UpbitOrderProgressError, match="requested order"):
        tracker.poll()
