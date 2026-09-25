from datetime import datetime, timezone
from decimal import Decimal

from investing_plz.domain import Bar, Instrument
from investing_plz.storage import SQLiteBarStore


INSTRUMENT = Instrument("upbit", "KRW-BTC")


def make_bar(day: int) -> Bar:
    return Bar(
        instrument=INSTRUMENT,
        interval="day",
        timestamp=datetime(2026, 9, day, tzinfo=timezone.utc),
        open=Decimal("100"),
        high=Decimal("120"),
        low=Decimal("90"),
        close=Decimal("110"),
        volume=Decimal("1"),
    )


def test_load_closed_bars_excludes_current_open_bar(tmp_path) -> None:
    store = SQLiteBarStore(tmp_path / "market.db")
    store.initialize()
    store.save([make_bar(23), make_bar(24), make_bar(25)])

    bars = store.load_closed_bars(
        INSTRUMENT,
        "day",
        now=datetime(2026, 9, 25, 12, tzinfo=timezone.utc),
    )

    assert [bar.timestamp.day for bar in bars] == [23, 24]


def test_dataset_summary_counts_range_and_quality(tmp_path) -> None:
    store = SQLiteBarStore(tmp_path / "market.db")
    store.initialize()
    store.save([make_bar(22), make_bar(23), make_bar(24), make_bar(25)])
    store.save([make_bar(24)])

    summary = store.summarize(
        INSTRUMENT,
        "day",
        now=datetime(2026, 9, 25, 12, tzinfo=timezone.utc),
    )

    assert summary.row_count == 4
    assert summary.closed_bar_count == 3
    assert summary.earliest_timestamp == make_bar(22).timestamp
    assert summary.latest_timestamp == make_bar(25).timestamp
    assert summary.latest_closed_timestamp == make_bar(24).timestamp
    assert summary.duplicate_count == 0
    assert summary.gap_count == 0


def test_dataset_summary_counts_missing_daily_candles(tmp_path) -> None:
    store = SQLiteBarStore(tmp_path / "market.db")
    store.initialize()
    store.save([make_bar(22), make_bar(24), make_bar(25)])

    summary = store.summarize(
        INSTRUMENT,
        "day",
        now=datetime(2026, 9, 26, tzinfo=timezone.utc),
    )

    assert summary.gap_count == 1
