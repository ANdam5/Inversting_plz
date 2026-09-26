import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from investing_plz.broker.models import ExecutionFill
from investing_plz.domain import Instrument, Order, OrderSide, OrderStatus
from investing_plz.domain.time import require_utc
from investing_plz.storage.paper import PaperCursorScope


class SQLitePaperRepository:
    """SQLite persistence for paper orders, fills, and processing cursors."""

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)

    def initialize(self) -> None:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS paper_orders (
                    order_id TEXT PRIMARY KEY,
                    venue TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    status TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS paper_fills (
                    fill_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    fill_price TEXT NOT NULL,
                    fee_amount TEXT NOT NULL,
                    filled_at TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    FOREIGN KEY (order_id) REFERENCES paper_orders(order_id)
                );

                CREATE TABLE IF NOT EXISTS paper_cursors (
                    venue TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    strategy_id TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    last_processed_bar_timestamp TEXT NOT NULL,
                    PRIMARY KEY (venue, symbol, strategy_id, timeframe)
                );
                """
            )

    def save_order(self, order: Order) -> None:
        if not isinstance(order, Order):
            raise TypeError("order must be an Order")
        with self._connect() as connection:
            row = connection.execute(
                _SELECT_ORDER + " WHERE order_id = ?", (order.order_id,)
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO paper_orders (
                        order_id, venue, symbol, side, quantity,
                        strategy_id, submitted_at, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _order_values(order),
                )
                return

            stored = _row_to_order(row)
            if _order_identity(stored) != _order_identity(order):
                raise ValueError(
                    f"order_id already exists with different order data: {order.order_id}"
                )
            if stored.status is order.status:
                return
            if stored.transition_to(order.status) != order:
                raise ValueError(f"invalid persisted order update: {order.order_id}")
            connection.execute(
                "UPDATE paper_orders SET status = ? WHERE order_id = ?",
                (order.status.value, order.order_id),
            )

    def get_order(self, order_id: str) -> Order | None:
        with self._connect() as connection:
            row = connection.execute(
                _SELECT_ORDER + " WHERE order_id = ?", (order_id,)
            ).fetchone()
        return None if row is None else _row_to_order(row)

    def list_orders(self) -> tuple[Order, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                _SELECT_ORDER + " ORDER BY submitted_at ASC, order_id ASC"
            ).fetchall()
        return tuple(_row_to_order(row) for row in rows)

    def list_open_orders(self) -> tuple[Order, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                _SELECT_ORDER
                + " WHERE status = ? ORDER BY submitted_at ASC, order_id ASC",
                (OrderStatus.PENDING.value,),
            ).fetchall()
        return tuple(_row_to_order(row) for row in rows)

    def save_fill(self, fill: ExecutionFill) -> bool:
        if not isinstance(fill, ExecutionFill):
            raise TypeError("fill must be an ExecutionFill")
        with self._connect() as connection:
            row = connection.execute(
                _SELECT_FILL + " WHERE fill_id = ?", (fill.fill_id,)
            ).fetchone()
            if row is not None:
                if _row_to_fill(row) != fill:
                    raise ValueError(
                        f"fill_id already exists with different fill data: {fill.fill_id}"
                    )
                return False
            try:
                connection.execute(
                    """
                    INSERT INTO paper_fills (
                        fill_id, order_id, venue, symbol, side, quantity,
                        fill_price, fee_amount, filled_at, strategy_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _fill_values(fill),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError(
                    f"fill references an unknown order_id: {fill.order_id}"
                ) from error
            return True

    def get_fill(self, fill_id: str) -> ExecutionFill | None:
        with self._connect() as connection:
            row = connection.execute(
                _SELECT_FILL + " WHERE fill_id = ?", (fill_id,)
            ).fetchone()
        return None if row is None else _row_to_fill(row)

    def list_fills(self) -> tuple[ExecutionFill, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                _SELECT_FILL + " ORDER BY filled_at ASC, fill_id ASC"
            ).fetchall()
        return tuple(_row_to_fill(row) for row in rows)

    def get_last_processed_bar_timestamp(
        self, scope: PaperCursorScope
    ) -> datetime | None:
        _require_scope(scope)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT last_processed_bar_timestamp
                FROM paper_cursors
                WHERE venue = ? AND symbol = ?
                  AND strategy_id = ? AND timeframe = ?
                """,
                _scope_values(scope),
            ).fetchone()
        return None if row is None else datetime.fromisoformat(row[0])

    def save_last_processed_bar_timestamp(
        self, scope: PaperCursorScope, timestamp: datetime
    ) -> None:
        _require_scope(scope)
        require_utc(timestamp)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO paper_cursors (
                    venue, symbol, strategy_id, timeframe,
                    last_processed_bar_timestamp
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (venue, symbol, strategy_id, timeframe)
                DO UPDATE SET
                    last_processed_bar_timestamp = excluded.last_processed_bar_timestamp
                """,
                (*_scope_values(scope), timestamp.isoformat()),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


_SELECT_ORDER = """
SELECT order_id, venue, symbol, side, quantity, strategy_id, submitted_at, status
FROM paper_orders
"""

_SELECT_FILL = """
SELECT fill_id, order_id, venue, symbol, side, quantity,
       fill_price, fee_amount, filled_at, strategy_id
FROM paper_fills
"""


def _order_values(order: Order) -> tuple[str, ...]:
    return (
        order.order_id,
        order.instrument.venue,
        order.instrument.symbol,
        order.side.value,
        str(order.quantity),
        order.strategy_id,
        order.submitted_at.isoformat(),
        order.status.value,
    )


def _order_identity(order: Order) -> tuple[object, ...]:
    return (
        order.order_id,
        order.instrument,
        order.side,
        order.quantity,
        order.strategy_id,
        order.submitted_at,
    )


def _row_to_order(row: tuple[str, ...]) -> Order:
    return Order(
        order_id=row[0],
        instrument=Instrument(row[1], row[2]),
        side=OrderSide(row[3]),
        quantity=Decimal(row[4]),
        strategy_id=row[5],
        submitted_at=datetime.fromisoformat(row[6]),
        status=OrderStatus(row[7]),
    )


def _fill_values(fill: ExecutionFill) -> tuple[str, ...]:
    return (
        fill.fill_id,
        fill.order_id,
        fill.instrument.venue,
        fill.instrument.symbol,
        fill.side.value,
        str(fill.quantity),
        str(fill.fill_price),
        str(fill.fee_amount),
        fill.filled_at.isoformat(),
        fill.strategy_id,
    )


def _row_to_fill(row: tuple[str, ...]) -> ExecutionFill:
    return ExecutionFill(
        fill_id=row[0],
        order_id=row[1],
        instrument=Instrument(row[2], row[3]),
        side=OrderSide(row[4]),
        quantity=Decimal(row[5]),
        fill_price=Decimal(row[6]),
        fee_amount=Decimal(row[7]),
        filled_at=datetime.fromisoformat(row[8]),
        strategy_id=row[9],
    )


def _scope_values(scope: PaperCursorScope) -> tuple[str, str, str, str]:
    return (
        scope.instrument.venue,
        scope.instrument.symbol,
        scope.strategy_id,
        scope.timeframe,
    )


def _require_scope(scope: PaperCursorScope) -> None:
    if not isinstance(scope, PaperCursorScope):
        raise TypeError("scope must be a PaperCursorScope")
