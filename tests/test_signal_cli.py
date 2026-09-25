from datetime import datetime, timezone
from decimal import Decimal

from investing_plz.cli import main
from investing_plz.domain import Bar, Instrument
from investing_plz.storage import SQLiteBarStore


def test_signal_cli_uses_only_closed_bars(tmp_path, capsys, monkeypatch) -> None:
    database = tmp_path / "market.db"
    instrument = Instrument("upbit", "KRW-BTC")
    closes = [3, 2, 1, 4, 100]
    bars = [
        Bar(
            instrument=instrument,
            interval="day",
            timestamp=datetime(2026, 9, day, tzinfo=timezone.utc),
            open=Decimal(close), high=Decimal(close), low=Decimal(close),
            close=Decimal(close), volume=Decimal("1"),
        )
        for day, close in zip(range(21, 26), closes)
    ]
    store = SQLiteBarStore(database)
    store.initialize()
    store.save(bars)
    monkeypatch.setattr(
        "investing_plz.cli._utc_now",
        lambda: datetime(2026, 9, 25, 12, tzinfo=timezone.utc),
    )

    result = main(
        [
            "signal", "--venue", "upbit", "--symbol", "KRW-BTC",
            "--timeframe", "day", "--database", str(database),
            "--fast", "2", "--slow", "3",
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "latest_closed_timestamp=2026-09-24T00:00:00+00:00" in output
    assert "latest_close=4" in output
    assert "latest_signal=bullish_crossover" in output
    assert "100" not in output
