import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from investing_plz.domain import Bar, Instrument


class BarTest(unittest.TestCase):
    def setUp(self) -> None:
        self.values = {
            "instrument": Instrument(venue="upbit", symbol="KRW-BTC"),
            "interval": "1m",
            "timestamp": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "open": Decimal("100"),
            "high": Decimal("120"),
            "low": Decimal("90"),
            "close": Decimal("110"),
            "volume": Decimal("1.5"),
        }

    def test_accepts_valid_ohlcv(self) -> None:
        bar = Bar(**self.values)

        self.assertEqual(bar.close, Decimal("110"))

    def test_rejects_naive_timestamp(self) -> None:
        self.values["timestamp"] = datetime(2026, 1, 1)

        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            Bar(**self.values)

    def test_rejects_non_utc_timestamp(self) -> None:
        self.values["timestamp"] = datetime(
            2026, 1, 1, tzinfo=timezone(timedelta(hours=9))
        )

        with self.assertRaisesRegex(ValueError, "UTC"):
            Bar(**self.values)

    def test_rejects_high_below_open_or_close(self) -> None:
        self.values["high"] = Decimal("105")

        with self.assertRaisesRegex(ValueError, "high"):
            Bar(**self.values)

    def test_rejects_low_above_open_or_close(self) -> None:
        self.values["low"] = Decimal("105")

        with self.assertRaisesRegex(ValueError, "low"):
            Bar(**self.values)

    def test_rejects_negative_price(self) -> None:
        self.values["open"] = Decimal("-1")

        with self.assertRaisesRegex(ValueError, "prices"):
            Bar(**self.values)

    def test_rejects_negative_volume(self) -> None:
        self.values["volume"] = Decimal("-0.1")

        with self.assertRaisesRegex(ValueError, "volume"):
            Bar(**self.values)


if __name__ == "__main__":
    unittest.main()

