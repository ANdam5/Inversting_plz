import unittest

from investing_plz.domain import Instrument


class InstrumentTest(unittest.TestCase):
    def test_identifies_upbit_krw_btc(self) -> None:
        instrument = Instrument(venue="upbit", symbol="KRW-BTC")

        self.assertEqual(instrument.venue, "upbit")
        self.assertEqual(instrument.symbol, "KRW-BTC")

    def test_rejects_empty_values(self) -> None:
        with self.assertRaises(ValueError):
            Instrument(venue="", symbol="KRW-BTC")
        with self.assertRaises(ValueError):
            Instrument(venue="upbit", symbol="   ")


if __name__ == "__main__":
    unittest.main()

