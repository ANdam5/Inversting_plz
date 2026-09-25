from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from investing_plz.cli import main
from investing_plz.domain import Bar, Instrument
from investing_plz.storage import SQLiteBarStore


def test_backtest_cli_reads_closed_bars_and_prints_result(tmp_path, capsys) -> None:
    database = tmp_path / "market.db"
    instrument = Instrument("upbit", "KRW-BTC")
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    closes = [Decimal(value) for value in ("3", "2", "1", "4", "5")]
    bars = [
        Bar(
            instrument=instrument,
            interval="day",
            timestamp=start + timedelta(days=index),
            open=Decimal("100") if index == 4 else close,
            high=max(Decimal("100") if index == 4 else close, close),
            low=min(Decimal("100") if index == 4 else close, close),
            close=close,
            volume=Decimal("1"),
        )
        for index, close in enumerate(closes)
    ]
    store = SQLiteBarStore(database)
    store.initialize()
    store.save(bars)

    with patch(
        "investing_plz.cli._utc_now",
        return_value=datetime(2024, 1, 7, tzinfo=timezone.utc),
    ):
        exit_code = main(
            [
                "backtest",
                "--venue", "upbit",
                "--symbol", "KRW-BTC",
                "--timeframe", "day",
                "--database", str(database),
                "--fast", "2",
                "--slow", "3",
                "--initial-cash", "1000",
                "--target-weight", "0.5",
                "--quantity-step", "1",
                "--max-order-amount", "10000",
                "--max-instrument-weight", "1",
                "--min-cash-reserve", "0",
            ]
        )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "closed_bar_count=5" in output
    assert "bullish_signal_count=1" in output
    assert "fill_count=1" in output
    assert "final_cash=500" in output
    assert "fee=0" in output
    assert "slippage=0" in output
