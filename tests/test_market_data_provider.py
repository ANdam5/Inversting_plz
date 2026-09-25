import unittest
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from investing_plz.domain import Bar, Instrument
from investing_plz.market_data import MarketDataProvider


class FakeMarketDataProvider:
    def __init__(self, bars: Sequence[Bar]) -> None:
        self._bars = bars

    def get_bars(self, instrument: Instrument, interval: str) -> Sequence[Bar]:
        return [
            bar
            for bar in self._bars
            if bar.instrument == instrument and bar.interval == interval
        ]


class MarketDataProviderTest(unittest.TestCase):
    def test_fake_provider_returns_matching_bars(self) -> None:
        instrument = Instrument(venue="upbit", symbol="KRW-BTC")
        expected = Bar(
            instrument=instrument,
            interval="1m",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            open=Decimal("100"),
            high=Decimal("120"),
            low=Decimal("90"),
            close=Decimal("110"),
            volume=Decimal("1.5"),
        )
        provider: MarketDataProvider = FakeMarketDataProvider([expected])

        self.assertEqual(provider.get_bars(instrument, "1m"), [expected])


if __name__ == "__main__":
    unittest.main()
