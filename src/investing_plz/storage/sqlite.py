import sqlite3
from collections.abc import Sequence
from pathlib import Path

from investing_plz.domain import Bar


class SQLiteBarStore:
    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)

    def initialize(self) -> None:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS bars (
                    venue TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open TEXT NOT NULL,
                    high TEXT NOT NULL,
                    low TEXT NOT NULL,
                    close TEXT NOT NULL,
                    volume TEXT NOT NULL,
                    PRIMARY KEY (venue, symbol, interval, timestamp)
                )
                """
            )

    def save(self, bars: Sequence[Bar]) -> int:
        rows = [
            (
                bar.instrument.venue,
                bar.instrument.symbol,
                bar.interval,
                bar.timestamp.isoformat(),
                str(bar.open),
                str(bar.high),
                str(bar.low),
                str(bar.close),
                str(bar.volume),
            )
            for bar in bars
        ]
        with sqlite3.connect(self.database) as connection:
            before = connection.total_changes
            connection.executemany(
                """
                INSERT OR IGNORE INTO bars (
                    venue, symbol, interval, timestamp,
                    open, high, low, close, volume
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            return connection.total_changes - before

    def count(self) -> int:
        with sqlite3.connect(self.database) as connection:
            row = connection.execute("SELECT COUNT(*) FROM bars").fetchone()
        return int(row[0])

