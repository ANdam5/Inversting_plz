from datetime import datetime, timezone
from decimal import Decimal

from investing_plz.application.collect import collect_bars
from investing_plz.domain import Bar, Instrument
from investing_plz.storage import SQLiteBarStore


class FakeProvider:
    def __init__(self, bar: Bar) -> None:
        self.bar = bar
        self.since_values = []

    def get_bars(
        self,
        instrument: Instrument,
        interval: str,
        *,
        since: datetime | None = None,
    ) -> list[Bar]:
        assert instrument == self.bar.instrument
        assert interval == self.bar.interval
        self.since_values.append(since)
        return [self.bar] if since is None or self.bar.timestamp > since else []


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

    provider = FakeProvider(bar)
    first = collect_bars(provider, store, instrument, "day")
    second = collect_bars(provider, store, instrument, "day")

    assert (first.fetched, first.inserted, first.total) == (1, 1, 1)
    assert (second.fetched, second.inserted, second.total) == (0, 0, 1)
    assert provider.since_values == [None, bar.timestamp]


def test_collection_resumes_after_existing_data(tmp_path) -> None:
    instrument = Instrument("upbit", "KRW-BTC")
    first_bar = Bar(
        instrument=instrument,
        interval="day",
        timestamp=datetime(2026, 9, 23, tzinfo=timezone.utc),
        open=Decimal("100"), high=Decimal("120"), low=Decimal("90"),
        close=Decimal("110"), volume=Decimal("1"),
    )
    second_bar = Bar(
        instrument=instrument,
        interval="day",
        timestamp=datetime(2026, 9, 24, tzinfo=timezone.utc),
        open=Decimal("110"), high=Decimal("130"), low=Decimal("100"),
        close=Decimal("120"), volume=Decimal("2"),
    )
    store = SQLiteBarStore(tmp_path / "market.db")
    first_provider = FakeProvider(first_bar)
    collect_bars(first_provider, store, instrument, "day")

    resumed_provider = FakeProvider(second_bar)
    result = collect_bars(resumed_provider, store, instrument, "day")

    assert resumed_provider.since_values == [first_bar.timestamp]
    assert (result.fetched, result.inserted, result.total) == (1, 1, 2)
