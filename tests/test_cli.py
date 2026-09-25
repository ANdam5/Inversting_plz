from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from investing_plz.cli import main
from investing_plz.domain import Bar, Instrument


class FakeProvider:
    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    def get_bars(self, instrument: Instrument, interval: str) -> list[Bar]:
        return [
            Bar(
                instrument=instrument,
                interval=interval,
                timestamp=datetime(2026, 9, 24, tzinfo=timezone.utc),
                open=Decimal("100"),
                high=Decimal("120"),
                low=Decimal("90"),
                close=Decimal("110"),
                volume=Decimal("1.5"),
            )
        ]


def test_collect_cli_without_network(tmp_path, capsys) -> None:
    database = tmp_path / "market.db"
    with patch("investing_plz.cli.UpbitMarketDataProvider", FakeProvider):
        result = main(
            [
                "collect",
                "--venue",
                "upbit",
                "--symbol",
                "KRW-BTC",
                "--timeframe",
                "day",
                "--database",
                str(database),
            ]
        )

    assert result == 0
    assert "fetched=1 inserted=1 total=1" in capsys.readouterr().out
    assert database.exists()

