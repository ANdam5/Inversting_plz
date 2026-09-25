import unittest


class ImportSmokeTest(unittest.TestCase):
    def test_package_imports(self) -> None:
        import investing_plz
        from investing_plz.domain import Bar, Instrument
        from investing_plz.market_data import MarketDataProvider

        self.assertIsNotNone(investing_plz)
        self.assertIsNotNone(Bar)
        self.assertIsNotNone(Instrument)
        self.assertIsNotNone(MarketDataProvider)


if __name__ == "__main__":
    unittest.main()

