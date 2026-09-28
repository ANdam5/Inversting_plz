from datetime import datetime, timezone
from decimal import Decimal
import sqlite3

import pytest

from investing_plz.adapters.upbit_execution import UpbitExecutionAccountingUpdate
from investing_plz.adapters.upbit_order import UpbitTradeSnapshot
from investing_plz.storage.upbit_live import UpbitExecutionLedgerConflictError
from investing_plz.storage.upbit_live_sqlite import SQLiteUpbitExecutionLedger


def trade(
    trade_id: str,
    *,
    order_market: str = "KRW-BTC",
    volume: str = "0.1",
    funds: str = "10.000000000000000000000000001",
    minute: int = 1,
) -> UpbitTradeSnapshot:
    return UpbitTradeSnapshot(
        trade_id=trade_id,
        market=order_market,
        side="bid",
        price=Decimal("100.12345678901234567890123456789"),
        volume=Decimal(volume),
        funds=Decimal(funds),
        created_at=datetime(2026, 9, 27, 0, minute, tzinfo=timezone.utc),
    )


def update(
    *trades: UpbitTradeSnapshot,
    order_id: str = "order-1",
    fee: str = "0.12345678901234567890123456789",
    executed: str | None = None,
    remaining: str = "0.9",
    state: str = "wait",
    trades_count: int | None = None,
) -> UpbitExecutionAccountingUpdate:
    return UpbitExecutionAccountingUpdate(
        order_id=order_id,
        newly_observed_trades=trades,
        cumulative_paid_fee=Decimal(fee),
        current_state=state,
        current_executed_volume=Decimal(
            executed
            if executed is not None
            else str(sum((item.volume for item in trades), Decimal("0")))
        ),
        current_remaining_volume=Decimal(remaining),
        current_trades_count=(len(trades) if trades_count is None else trades_count),
    )


def test_initialize_apply_and_reopen_round_trip(tmp_path) -> None:
    database = tmp_path / "live.db"
    first = SQLiteUpbitExecutionLedger(database)
    first.initialize()
    trade_a = trade("trade-a")

    result = first.apply_update(update(trade_a))

    assert result.inserted_trade_ids == ("trade-a",)
    assert result.order_state_changed is True
    reopened = SQLiteUpbitExecutionLedger(database)
    reopened.initialize()
    assert reopened.get_trade("trade-a") == trade_a
    state = reopened.get_order_accounting_state("order-1")
    assert state is not None
    assert state.cumulative_paid_fee == Decimal(
        "0.12345678901234567890123456789"
    )
    assert state.executed_volume == Decimal("0.1")
    assert state.remaining_volume == Decimal("0.9")
    assert state.trades_count == 1
    assert state.state == "wait"


def test_identical_trade_and_order_state_replay_is_idempotent(tmp_path) -> None:
    ledger = SQLiteUpbitExecutionLedger(tmp_path / "live.db")
    ledger.initialize()
    value = update(trade("trade-a"))
    ledger.apply_update(value)

    result = ledger.apply_update(value)

    assert result.inserted_trade_ids == ()
    assert result.order_state_changed is False
    assert tuple(item.trade_id for item in ledger.list_trades("order-1")) == (
        "trade-a",
    )


def test_same_trade_id_with_changed_content_or_order_is_rejected(tmp_path) -> None:
    ledger = SQLiteUpbitExecutionLedger(tmp_path / "live.db")
    ledger.initialize()
    ledger.apply_update(update(trade("trade-a")))

    with pytest.raises(UpbitExecutionLedgerConflictError, match="trade identity"):
        ledger.apply_update(update(trade("trade-a", volume="0.2"), executed="0.2"))
    with pytest.raises(UpbitExecutionLedgerConflictError, match="trade identity"):
        ledger.apply_update(
            update(trade("trade-a"), order_id="order-2", executed="0.1")
        )


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ({"fee": "0.1"}, "cumulative fee regression"),
        ({"executed": "0.05"}, "executed volume regression"),
        ({"trades_count": 0}, "trades count regression"),
    ],
)
def test_cumulative_accounting_regression_is_rejected(
    tmp_path, replacement, message
) -> None:
    ledger = SQLiteUpbitExecutionLedger(tmp_path / "live.db")
    ledger.initialize()
    ledger.apply_update(update(trade("trade-a"), fee="0.2", executed="0.1"))

    values = {"fee": "0.2", "executed": "0.1"}
    values.update(replacement)
    with pytest.raises(UpbitExecutionLedgerConflictError, match=message):
        ledger.apply_update(update(**values))


@pytest.mark.parametrize("terminal_state", ["done", "cancel"])
def test_terminal_state_cannot_return_to_non_terminal(tmp_path, terminal_state) -> None:
    ledger = SQLiteUpbitExecutionLedger(tmp_path / "live.db")
    ledger.initialize()
    ledger.apply_update(update(state=terminal_state, remaining="0"))

    with pytest.raises(UpbitExecutionLedgerConflictError, match="state regression"):
        ledger.apply_update(update(state="wait", remaining="0"))


def test_multiple_trades_are_atomic_and_deterministically_ordered(tmp_path) -> None:
    ledger = SQLiteUpbitExecutionLedger(tmp_path / "live.db")
    ledger.initialize()
    trade_b = trade("trade-b", volume="0.2", minute=2)
    trade_a = trade("trade-a", volume="0.1", minute=1)

    result = ledger.apply_update(
        update(trade_b, trade_a, executed="0.3", remaining="0.7")
    )

    assert result.inserted_trade_ids == ("trade-b", "trade-a")
    assert tuple(item.trade_id for item in ledger.list_trades("order-1")) == (
        "trade-a",
        "trade-b",
    )


def test_restart_replay_keeps_existing_trade_and_adds_only_new_trade(tmp_path) -> None:
    database = tmp_path / "live.db"
    trade_a = trade("trade-a", volume="0.4", minute=1)
    trade_b = trade("trade-b", volume="0.3", minute=2)
    first = SQLiteUpbitExecutionLedger(database)
    first.initialize()
    first.apply_update(
        update(trade_a, fee="100", executed="0.4", remaining="0.6")
    )

    restarted = SQLiteUpbitExecutionLedger(database)
    restarted.initialize()
    result = restarted.apply_update(
        update(
            trade_a,
            trade_b,
            fee="175",
            executed="0.7",
            remaining="0.3",
        )
    )

    assert result.inserted_trade_ids == ("trade-b",)
    assert tuple(item.trade_id for item in restarted.list_trades("order-1")) == (
        "trade-a",
        "trade-b",
    )
    assert restarted.get_order_accounting_state(
        "order-1"
    ).cumulative_paid_fee == Decimal("175")


def test_completed_first_observation_and_replay_are_idempotent(tmp_path) -> None:
    database = tmp_path / "live.db"
    trades = tuple(
        trade(f"trade-{name}", volume="0.3", minute=index)
        for index, name in enumerate(("a", "b", "c"), start=1)
    )
    first = SQLiteUpbitExecutionLedger(database)
    first.initialize()
    final = update(
        *trades,
        fee="300",
        executed="0.9",
        remaining="0",
        state="done",
    )
    first.apply_update(final)

    restarted = SQLiteUpbitExecutionLedger(database)
    restarted.initialize()
    result = restarted.apply_update(final)

    assert result.inserted_trade_ids == ()
    assert result.order_state_changed is False
    assert len(restarted.list_trades("order-1")) == 3


def test_partial_then_cancel_preserves_trades(tmp_path) -> None:
    ledger = SQLiteUpbitExecutionLedger(tmp_path / "live.db")
    ledger.initialize()
    trade_a = trade("trade-a", volume="0.4", minute=1)
    trade_b = trade("trade-b", volume="0.2", minute=2)
    ledger.apply_update(
        update(trade_a, fee="100", executed="0.4", remaining="0.6")
    )

    ledger.apply_update(
        update(
            trade_b,
            fee="150",
            executed="0.6",
            remaining="0.4",
            state="cancel",
            trades_count=2,
        )
    )

    assert tuple(item.trade_id for item in ledger.list_trades("order-1")) == (
        "trade-a",
        "trade-b",
    )
    assert ledger.get_order_accounting_state("order-1").state == "cancel"


def test_invalid_state_update_rolls_back_new_trade(tmp_path) -> None:
    ledger = SQLiteUpbitExecutionLedger(tmp_path / "live.db")
    ledger.initialize()
    ledger.apply_update(
        update(trade("trade-a"), fee="100", executed="0.1", remaining="0.9")
    )

    with pytest.raises(
        UpbitExecutionLedgerConflictError, match="cumulative fee regression"
    ):
        ledger.apply_update(
            update(
                trade("trade-b", minute=2),
                fee="90",
                executed="0.2",
                remaining="0.8",
                trades_count=2,
            )
        )

    assert ledger.get_trade("trade-b") is None
    assert ledger.get_order_accounting_state(
        "order-1"
    ).cumulative_paid_fee == Decimal("100")


def test_schema_has_no_per_trade_fee_column(tmp_path) -> None:
    database = tmp_path / "live.db"
    ledger = SQLiteUpbitExecutionLedger(database)
    ledger.initialize()

    with sqlite3.connect(database) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(live_upbit_trades)")
        }

    assert "fee" not in columns
    assert "fee_amount" not in columns
