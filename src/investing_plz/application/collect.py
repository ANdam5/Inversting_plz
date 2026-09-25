from dataclasses import dataclass

from investing_plz.domain import Instrument
from investing_plz.market_data import MarketDataProvider
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
    bars = provider.get_bars(instrument, interval)
    store.initialize()
    inserted = store.save(bars)
    return CollectionResult(fetched=len(bars), inserted=inserted, total=store.count())

