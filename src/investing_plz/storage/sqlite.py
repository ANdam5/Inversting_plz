import sqlite3
from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from investing_plz.domain import Bar, Instrument
from investing_plz.domain.time import require_utc
from investing_plz.market_data import DatasetSummary, is_closed_bar
from investing_plz.market_data.candles import is_closed_timestamp


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

    def latest_timestamp(
        self, instrument: Instrument, interval: str
    ) -> datetime | None:
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                """
                SELECT MAX(timestamp) FROM bars
                WHERE venue = ? AND symbol = ? AND interval = ?
                """,
                (instrument.venue, instrument.symbol, interval),
            ).fetchone()
        return datetime.fromisoformat(row[0]) if row and row[0] is not None else None

    def load_closed_bars(
        self,
        instrument: Instrument,
        interval: str,
        *,
        now: datetime,
    ) -> list[Bar]:
        require_utc(now)
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                """
                SELECT timestamp, open, high, low, close, volume
                FROM bars
                WHERE venue = ? AND symbol = ? AND interval = ?
                ORDER BY timestamp ASC
                """,
                (instrument.venue, instrument.symbol, interval),
            ).fetchall()
        bars = [_row_to_bar(row, instrument, interval) for row in rows]
        return [bar for bar in bars if is_closed_bar(bar, now=now)]

    def summarize(
        self,
        instrument: Instrument,
        interval: str,
        *,
        now: datetime,
    ) -> DatasetSummary:
        require_utc(now)
        with sqlite3.connect(self.database) as connection:
            rows = connection.execute(
                """
                SELECT timestamp, COUNT(*)
                FROM bars
                WHERE venue = ? AND symbol = ? AND interval = ?
                GROUP BY timestamp
                ORDER BY timestamp ASC
                """,
                (instrument.venue, instrument.symbol, interval),
            ).fetchall()

        timestamps = [datetime.fromisoformat(row[0]) for row in rows]
        duplicate_count = sum(int(row[1]) - 1 for row in rows)
        closed = [
            timestamp
            for timestamp in timestamps
            if is_closed_timestamp(timestamp, interval, now=now)
        ]
        gap_count = _daily_gap_count(timestamps, interval)
        return DatasetSummary(
            venue=instrument.venue,
            symbol=instrument.symbol,
            timeframe=interval,
            row_count=sum(int(row[1]) for row in rows),
            closed_bar_count=len(closed),
            earliest_timestamp=timestamps[0] if timestamps else None,
            latest_timestamp=timestamps[-1] if timestamps else None,
            latest_closed_timestamp=closed[-1] if closed else None,
            duplicate_count=duplicate_count,
            gap_count=gap_count,
        )

    def count(
        self,
        instrument: Instrument | None = None,
        interval: str | None = None,
    ) -> int:
        with sqlite3.connect(self.database) as connection:
            if instrument is None:
                row = connection.execute("SELECT COUNT(*) FROM bars").fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT COUNT(*) FROM bars
                    WHERE venue = ? AND symbol = ? AND interval = ?
                    """,
                    (instrument.venue, instrument.symbol, interval),
                ).fetchone()
        return int(row[0])


def _row_to_bar(
    row: tuple[str, str, str, str, str, str],
    instrument: Instrument,
    interval: str,
) -> Bar:
    return Bar(
        instrument=instrument,
        interval=interval,
        timestamp=datetime.fromisoformat(row[0]),
        open=Decimal(row[1]),
        high=Decimal(row[2]),
        low=Decimal(row[3]),
        close=Decimal(row[4]),
        volume=Decimal(row[5]),
    )


def _daily_gap_count(timestamps: list[datetime], interval: str) -> int:
    if interval != "day":
        raise ValueError("dataset summary currently supports only day bars")
    step = timedelta(days=1)
    return sum(
        max(0, int((later - earlier) / step) - 1)
        for earlier, later in zip(timestamps, timestamps[1:])
    )
