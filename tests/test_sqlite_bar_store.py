import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

from investing_plz.domain import Bar, Instrument
from investing_plz.storage import SQLiteBarStore


def make_bar() -> Bar:
    return Bar(
        instrument=Instrument("upbit", "KRW-BTC"),
        interval="day",
        timestamp=datetime(2026, 9, 24, tzinfo=timezone.utc),
        open=Decimal("100"),
        high=Decimal("120"),
        low=Decimal("90"),
        close=Decimal("110"),
        volume=Decimal("1.5"),
    )


def test_save_round_trip_values(tmp_path) -> None:
    database = tmp_path / "market.db"
    store = SQLiteBarStore(database)
    store.initialize()

    assert store.save([make_bar()]) == 1

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT venue, symbol, interval, timestamp, open, close, volume FROM bars"
        ).fetchone()
    assert row == (
        "upbit",
        "KRW-BTC",
        "day",
        "2026-09-24T00:00:00+00:00",
        "100",
        "110",
        "1.5",
    )


def test_duplicate_bar_is_ignored(tmp_path) -> None:
    store = SQLiteBarStore(tmp_path / "market.db")
    store.initialize()

    assert store.save([make_bar()]) == 1
    assert store.save([make_bar()]) == 0
    assert store.count() == 1

