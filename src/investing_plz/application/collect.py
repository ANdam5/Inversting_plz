from dataclasses import dataclass

from investing_plz.domain import Instrument
from investing_plz.market_data import MarketDataProvider
from investing_plz.market_data.validation import validate_bar_series
from investing_plz.storage import SQLiteBarStore


@dataclass(frozen=True, slots=True)
class CollectionResult:
    fetched: int
    inserted: int
    total: int


def collect_bars(
    provider: MarketDataProvider,
    store: SQLiteBarStore,
    instrument: Instrument,
    interval: str,
) -> CollectionResult:
    store.initialize()
    latest = store.latest_timestamp(instrument, interval)
    bars = provider.get_bars(instrument, interval, since=latest)
    validate_bar_series(bars, interval, previous_timestamp=latest)
    new_bars = [bar for bar in bars if latest is None or bar.timestamp > latest]
    inserted = store.save(new_bars)
    return CollectionResult(
        fetched=len(bars),
        inserted=inserted,
        total=store.count(instrument, interval),
    )
