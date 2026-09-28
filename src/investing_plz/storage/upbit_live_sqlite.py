import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from investing_plz.adapters.upbit_execution import UpbitExecutionAccountingUpdate
from investing_plz.adapters.upbit_order import UpbitTradeSnapshot
from investing_plz.storage.upbit_live import (
    UpbitExecutionLedgerApplyResult,
    UpbitExecutionLedgerConflictError,
    UpbitPersistedOrderAccountingState,
    _require_order_id,
)


_TERMINAL_STATES = frozenset(("done", "cancel"))


class SQLiteUpbitExecutionLedger:
    """SQLite ledger for exact Upbit REST trade and cumulative fee facts."""

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)

    def initialize(self) -> None:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS live_upbit_trades (
                    trade_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    market TEXT NOT NULL,
                    side TEXT NOT NULL,
                    price TEXT NOT NULL,
                    volume TEXT NOT NULL,
                    funds TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS live_upbit_order_accounting (
                    order_id TEXT PRIMARY KEY,
                    cumulative_paid_fee TEXT NOT NULL,
                    executed_volume TEXT NOT NULL,
                    remaining_volume TEXT NOT NULL,
                    state TEXT NOT NULL,
                    trades_count INTEGER NOT NULL
                );
                """
            )

    def apply_update(
        self, update: UpbitExecutionAccountingUpdate
    ) -> UpbitExecutionLedgerApplyResult:
        if not isinstance(update, UpbitExecutionAccountingUpdate):
            raise TypeError("update must be an UpbitExecutionAccountingUpdate")

        with self._connect() as connection:
            state_row = connection.execute(
                _SELECT_ORDER_STATE + " WHERE order_id = ?", (update.order_id,)
            ).fetchone()
            stored_state = (
                None if state_row is None else _row_to_order_state(state_row)
            )
            _validate_state_progress(stored_state, update)

            new_trades: list[UpbitTradeSnapshot] = []
            for incoming in update.newly_observed_trades:
                row = connection.execute(
                    _SELECT_TRADE + " WHERE trade_id = ?", (incoming.trade_id,)
                ).fetchone()
                if row is None:
                    new_trades.append(incoming)
                    continue
                stored_order_id, stored_trade = _row_to_order_trade(row)
                if stored_order_id != update.order_id or stored_trade != incoming:
                    raise UpbitExecutionLedgerConflictError(
                        f"conflicting trade identity: {incoming.trade_id}"
                    )

            for incoming in new_trades:
                connection.execute(
                    """
                    INSERT INTO live_upbit_trades (
                        trade_id, order_id, market, side, price,
                        volume, funds, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _trade_values(update.order_id, incoming),
                )

            incoming_state = _state_from_update(update)
            state_changed = stored_state != incoming_state
            if stored_state is None:
                connection.execute(
                    """
                    INSERT INTO live_upbit_order_accounting (
                        order_id, cumulative_paid_fee, executed_volume,
                        remaining_volume, state, trades_count
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    _state_values(incoming_state),
                )
            elif state_changed:
                connection.execute(
                    """
                    UPDATE live_upbit_order_accounting
                    SET cumulative_paid_fee = ?, executed_volume = ?,
                        remaining_volume = ?, state = ?, trades_count = ?
                    WHERE order_id = ?
                    """,
                    (
                        str(incoming_state.cumulative_paid_fee),
                        str(incoming_state.executed_volume),
                        str(incoming_state.remaining_volume),
                        incoming_state.state,
                        incoming_state.trades_count,
                        incoming_state.order_id,
                    ),
                )

        return UpbitExecutionLedgerApplyResult(
            inserted_trade_ids=tuple(trade.trade_id for trade in new_trades),
            order_state_changed=state_changed,
        )

    def get_trade(self, trade_id: str) -> UpbitTradeSnapshot | None:
        _require_trade_id(trade_id)
        with self._connect() as connection:
            row = connection.execute(
                _SELECT_TRADE + " WHERE trade_id = ?", (trade_id,)
            ).fetchone()
        return None if row is None else _row_to_order_trade(row)[1]

    def list_trades(
        self, order_id: str | None = None
    ) -> tuple[UpbitTradeSnapshot, ...]:
        if order_id is None:
            query = _SELECT_TRADE + " ORDER BY order_id, created_at, trade_id"
            parameters: tuple[str, ...] = ()
        else:
            _require_order_id(order_id)
            query = (
                _SELECT_TRADE
                + " WHERE order_id = ? ORDER BY created_at, trade_id"
            )
            parameters = (order_id,)
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(_row_to_order_trade(row)[1] for row in rows)

    def get_order_accounting_state(
        self, order_id: str
    ) -> UpbitPersistedOrderAccountingState | None:
        _require_order_id(order_id)
        with self._connect() as connection:
            row = connection.execute(
                _SELECT_ORDER_STATE + " WHERE order_id = ?", (order_id,)
            ).fetchone()
        return None if row is None else _row_to_order_state(row)

    def list_order_accounting_states(
        self,
    ) -> tuple[UpbitPersistedOrderAccountingState, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                _SELECT_ORDER_STATE + " ORDER BY order_id"
            ).fetchall()
        return tuple(_row_to_order_state(row) for row in rows)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database)


_SELECT_TRADE = """
SELECT trade_id, order_id, market, side, price, volume, funds, created_at
FROM live_upbit_trades
"""

_SELECT_ORDER_STATE = """
SELECT order_id, cumulative_paid_fee, executed_volume,
       remaining_volume, state, trades_count
FROM live_upbit_order_accounting
"""


def _trade_values(
    order_id: str, trade: UpbitTradeSnapshot
) -> tuple[str, ...]:
    return (
        trade.trade_id,
        order_id,
        trade.market,
        trade.side,
        str(trade.price),
        str(trade.volume),
        str(trade.funds),
        trade.created_at.isoformat(),
    )


def _row_to_order_trade(
    row: tuple[object, ...],
) -> tuple[str, UpbitTradeSnapshot]:
    created_at = datetime.fromisoformat(str(row[7]))
    if created_at.tzinfo is None or created_at.utcoffset() != timezone.utc.utcoffset(
        created_at
    ):
        raise ValueError("persisted trade created_at must be UTC-aware")
    return (
        str(row[1]),
        UpbitTradeSnapshot(
            trade_id=str(row[0]),
            market=str(row[2]),
            side=str(row[3]),
            price=Decimal(str(row[4])),
            volume=Decimal(str(row[5])),
            funds=Decimal(str(row[6])),
            created_at=created_at,
        ),
    )


def _state_from_update(
    update: UpbitExecutionAccountingUpdate,
) -> UpbitPersistedOrderAccountingState:
    return UpbitPersistedOrderAccountingState(
        order_id=update.order_id,
        cumulative_paid_fee=update.cumulative_paid_fee,
        executed_volume=update.current_executed_volume,
        remaining_volume=update.current_remaining_volume,
        state=update.current_state,
        trades_count=update.current_trades_count,
    )


def _state_values(
    state: UpbitPersistedOrderAccountingState,
) -> tuple[object, ...]:
    return (
        state.order_id,
        str(state.cumulative_paid_fee),
        str(state.executed_volume),
        str(state.remaining_volume),
        state.state,
        state.trades_count,
    )


def _row_to_order_state(
    row: tuple[object, ...],
) -> UpbitPersistedOrderAccountingState:
    return UpbitPersistedOrderAccountingState(
        order_id=str(row[0]),
        cumulative_paid_fee=Decimal(str(row[1])),
        executed_volume=Decimal(str(row[2])),
        remaining_volume=Decimal(str(row[3])),
        state=str(row[4]),
        trades_count=int(row[5]),
    )


def _validate_state_progress(
    stored: UpbitPersistedOrderAccountingState | None,
    update: UpbitExecutionAccountingUpdate,
) -> None:
    if stored is None:
        return
    if update.cumulative_paid_fee < stored.cumulative_paid_fee:
        raise UpbitExecutionLedgerConflictError("cumulative fee regression")
    if update.current_executed_volume < stored.executed_volume:
        raise UpbitExecutionLedgerConflictError("executed volume regression")
    if update.current_trades_count < stored.trades_count:
        raise UpbitExecutionLedgerConflictError("trades count regression")
    if stored.state in _TERMINAL_STATES and update.current_state not in _TERMINAL_STATES:
        raise UpbitExecutionLedgerConflictError("invalid state regression")


def _require_trade_id(trade_id: object) -> str:
    if (
        not isinstance(trade_id, str)
        or not trade_id
        or trade_id != trade_id.strip()
    ):
        raise ValueError("trade_id must be a non-empty unpadded string")
    return trade_id
