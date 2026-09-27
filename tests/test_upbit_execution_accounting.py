from collections.abc import Sequence
from decimal import Decimal

import pytest

from investing_plz.adapters.upbit_execution import (
    UpbitExecutionAccountingUpdate,
    upbit_order_progress_to_accounting_update,
)
from investing_plz.adapters.upbit_order import upbit_order_response_to_snapshot
from investing_plz.adapters.upbit_order_tracker import (
    UpbitOrderTracker,
    compare_upbit_order_progress,
)


def trade(
    trade_id: str,
    *,
    volume: str,
    funds: str,
    price: str = "100",
    minute: int = 1,
) -> dict[str, object]:
    return {
        "market": "KRW-BTC",
        "uuid": trade_id,
        "price": price,
        "volume": volume,
        "funds": funds,
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
):
    return upbit_order_response_to_snapshot(
        {
            "uuid": "order-1",
            "side": "bid",
            "ord_type": "limit",
            "price": "100",
            "state": state,
            "market": "KRW-BTC",
            "created_at": "2026-09-27T00:00:00Z",
            "volume": "1",
            "remaining_volume": remaining,
            "reserved_fee": "0.5",
            "remaining_fee": "0.5",
            "paid_fee": paid_fee,
            "locked": "100.5",
            "executed_volume": executed,
            "trades_count": len(trades),
            "trades": list(trades),
        }
    )


class SequenceSource:
    def __init__(self, snapshots) -> None:
        self._snapshots = iter(snapshots)

    def get_order(self, order_id: str):
        return next(self._snapshots)


def update(previous, current):
    return upbit_order_progress_to_accounting_update(
        compare_upbit_order_progress(previous, current)
    )


def test_initial_unfilled_observation_has_zero_fee_and_no_trade_delta() -> None:
    tracker = UpbitOrderTracker("order-1", SequenceSource([snapshot()]))

    result = upbit_order_progress_to_accounting_update(tracker.poll())

    assert result.newly_observed_trades == ()
    assert result.cumulative_paid_fee == Decimal("0")
    assert result.executed_quantity_delta == Decimal("0")
    assert result.executed_notional_delta == Decimal("0")
    assert result.weighted_average_price is None


def test_first_and_additional_partial_updates_keep_cumulative_fee_separate() -> None:
    trade_a = trade("trade-a", volume="0.4", funds="40", minute=1)
    trade_b = trade("trade-b", volume="0.3", funds="30", minute=2)
    empty = snapshot()
    first_partial = snapshot(
        executed="0.4", remaining="0.6", paid_fee="100", trades=[trade_a]
    )
    additional = snapshot(
        executed="0.7",
        remaining="0.3",
        paid_fee="175",
        trades=[trade_a, trade_b],
    )

    first = update(empty, first_partial)
    second = update(first_partial, additional)

    assert tuple(item.trade_id for item in first.newly_observed_trades) == ("trade-a",)
    assert first.cumulative_paid_fee == Decimal("100")
    assert tuple(item.trade_id for item in second.newly_observed_trades) == ("trade-b",)
    assert second.cumulative_paid_fee == Decimal("175")
    assert not hasattr(second.newly_observed_trades[0], "fee_amount")


def test_multiple_trades_between_polls_sum_volume_and_exchange_funds() -> None:
    trade_a = trade("trade-a", volume="0.2", funds="20", minute=1)
    trade_b = trade(
        "trade-b", volume="0.3", price="100", funds="29.99999999", minute=2
    )
    trade_c = trade("trade-c", volume="0.5", funds="50.00000001", minute=3)

    result = update(
        snapshot(executed="0.2", remaining="0.8", trades=[trade_a]),
        snapshot(
            executed="1",
            remaining="0",
            paid_fee="0.5",
            trades=[trade_a, trade_b, trade_c],
        ),
    )

    assert tuple(item.trade_id for item in result.newly_observed_trades) == (
        "trade-b",
        "trade-c",
    )
    assert result.executed_quantity_delta == Decimal("0.8")
    assert result.executed_notional_delta == Decimal("80.00000000")
    assert result.weighted_average_price == Decimal("100.0000000")


def test_identical_poll_has_no_accounting_trade_delta() -> None:
    current = snapshot(
        executed="0.4",
        remaining="0.6",
        paid_fee="0.2",
        trades=[trade("trade-a", volume="0.4", funds="40")],
    )

    result = update(current, current)

    assert result.newly_observed_trades == ()
    assert result.cumulative_paid_fee == Decimal("0.2")
    assert result.weighted_average_price is None


@pytest.mark.parametrize("state", ["wait", "done", "cancel"])
def test_first_observation_after_restart_recovers_all_visible_trades(state: str) -> None:
    trades = [
        trade("trade-a", volume="0.4", funds="40", minute=1),
        trade("trade-b", volume="0.3", funds="30", minute=2),
    ]
    current = snapshot(
        state=state,
        executed="0.7",
        remaining="0.3",
        paid_fee="175.1234567890123456789",
        trades=trades,
    )
    tracker = UpbitOrderTracker("order-1", SequenceSource([current]))

    result = upbit_order_progress_to_accounting_update(tracker.poll())

    assert tuple(item.trade_id for item in result.newly_observed_trades) == (
        "trade-a",
        "trade-b",
    )
    assert result.cumulative_paid_fee == Decimal("175.1234567890123456789")
    assert result.current_state == state
    assert result.current_executed_volume == Decimal("0.7")


def test_partial_then_cancel_keeps_prior_trades_as_accounting_facts() -> None:
    trades = [
        trade("trade-a", volume="0.4", funds="40", minute=1),
        trade("trade-b", volume="0.2", funds="20", minute=2),
    ]
    partial = snapshot(
        executed="0.4", remaining="0.6", paid_fee="0.2", trades=trades[:1]
    )
    canceled = snapshot(
        state="cancel",
        executed="0.6",
        remaining="0.4",
        paid_fee="0.3",
        trades=trades,
    )

    result = update(partial, canceled)

    assert result.current_state == "cancel"
    assert tuple(item.trade_id for item in result.newly_observed_trades) == ("trade-b",)
    assert result.current_executed_volume == Decimal("0.6")


@pytest.mark.parametrize(
    "fee",
    [Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), 0.1],
)
def test_accounting_update_rejects_invalid_cumulative_fee(fee: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        UpbitExecutionAccountingUpdate(
            order_id="order-1",
            newly_observed_trades=(),
            cumulative_paid_fee=fee,  # type: ignore[arg-type]
            current_state="wait",
            current_executed_volume=Decimal("0"),
            current_remaining_volume=Decimal("1"),
            current_trades_count=0,
        )
