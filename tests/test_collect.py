from datetime import datetime, timezone
from decimal import Decimal

from investing_plz.application.collect import collect_bars
from investing_plz.domain import Bar, Instrument
from investing_plz.storage import SQLiteBarStore


class FakeProvider:
    def __init__(self, bar: Bar) -> None:
        self.bar = bar

    def get_bars(self, instrument: Instrument, interval: str) -> list[Bar]:
        assert instrument == self.bar.instrument
        assert interval == self.bar.interval
        return [self.bar]


def test_collection_is_idempotent(tmp_path) -> None:
    instrument = Instrument("upbit", "KRW-BTC")
    bar = Bar(
        instrument=instrument,
        interval="day",
        timestamp=datetime(2026, 9, 24, tzinfo=timezone.utc),
        open=Decimal("100"),
        high=Decimal("120"),
        low=Decimal("90"),
        close=Decimal("110"),
        volume=Decimal("1.5"),
    )
    store = SQLiteBarStore(tmp_path / "market.db")

    first = collect_bars(FakeProvider(bar), store, instrument, "day")
    second = collect_bars(FakeProvider(bar), store, instrument, "day")

    assert (first.fetched, first.inserted, first.total) == (1, 1, 1)
    assert (second.fetched, second.inserted, second.total) == (1, 0, 1)

