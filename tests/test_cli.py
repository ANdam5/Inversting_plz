from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from investing_plz.cli import main
from investing_plz.domain import Bar, Instrument


class FakeProvider:
    def __init__(self, *, timeout: float, max_pages: int) -> None:
        self.timeout = timeout
        self.max_pages = max_pages

    def get_bars(
        self,
        instrument: Instrument,
        interval: str,
        *,
        since: datetime | None = None,
    ) -> list[Bar]:
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


def test_summary_cli(tmp_path, capsys) -> None:
    database = tmp_path / "market.db"
    instrument = Instrument("upbit", "KRW-BTC")
    from investing_plz.storage import SQLiteBarStore

    store = SQLiteBarStore(database)
    store.initialize()
    store.save(
        [
            Bar(
                instrument=instrument,
                interval="day",
                timestamp=datetime(2026, 9, 24, tzinfo=timezone.utc),
                open=Decimal("100"), high=Decimal("120"), low=Decimal("90"),
                close=Decimal("110"), volume=Decimal("1"),
            )
        ]
    )

    with patch(
        "investing_plz.cli._utc_now",
        return_value=datetime(2026, 9, 25, tzinfo=timezone.utc),
    ):
        assert main(
            [
                "summary", "--venue", "upbit", "--symbol", "KRW-BTC",
                "--timeframe", "day", "--database", str(database),
            ]
        ) == 0

    output = capsys.readouterr().out
    assert "row_count=1" in output
    assert "closed_bar_count=1" in output
    assert "duplicate_count=0" in output
    assert "gap_count=0" in output
