from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from investing_plz.cli import main
from investing_plz.domain import Bar, Instrument
from investing_plz.storage import SQLiteBarStore


def _save_bars(database, closes: tuple[str, ...], opens: dict[int, str]) -> None:
    instrument = Instrument("upbit", "KRW-BTC")
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = []
    for index, close_text in enumerate(closes):
        close = Decimal(close_text)
        open_price = Decimal(opens.get(index, close_text))
        bars.append(
            Bar(
                instrument=instrument,
                interval="day",
                timestamp=start + timedelta(days=index),
                open=open_price,
                high=max(open_price, close),
                low=min(open_price, close),
                close=close,
                volume=Decimal("1"),
            )
        )
    store = SQLiteBarStore(database)
    store.initialize()
    store.save(bars)


def _run_backtest_cli(database, *, show_fills: bool) -> int:
    args = [
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
        "--min-trade-amount", "10",
        "--max-order-amount", "10000",
        "--max-instrument-weight", "1",
        "--min-cash-reserve", "0",
    ]
    if show_fills:
        args.append("--show-fills")
    with patch(
        "investing_plz.cli._utc_now",
        return_value=datetime(2024, 1, 10, tzinfo=timezone.utc),
    ):
        return main(args)


def _output_value(output: str, key: str) -> str:
    prefix = f"{key}="
    return next(line.removeprefix(prefix) for line in output.splitlines() if line.startswith(prefix))


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
    assert "fills:" not in output


def test_show_fills_prints_all_fills_in_time_order_with_amount(tmp_path, capsys) -> None:
    database = tmp_path / "multiple-fills.db"
    _save_bars(
        database,
        ("3", "2", "1", "4", "0", "0", "1"),
        {4: "100", 6: "80"},
    )

    assert _run_backtest_cli(database, show_fills=True) == 0

    output = capsys.readouterr().out
    first = (
        "1. timestamp=2024-01-05T00:00:00+00:00 side=BUY quantity=5 "
        "fill_price=100 amount=500 strategy_id=moving_average_crossover"
    )
    second = (
        "2. timestamp=2024-01-07T00:00:00+00:00 side=SELL quantity=5 "
        "fill_price=80 amount=400 strategy_id=moving_average_crossover"
    )
    assert "fills:\n" in output
    assert first in output
    assert second in output
    assert output.index(first) < output.index(second)


def test_show_fills_handles_backtest_with_no_fills(tmp_path, capsys) -> None:
    database = tmp_path / "no-fills.db"
    _save_bars(database, ("1", "2", "3", "4", "5"), {})

    assert _run_backtest_cli(database, show_fills=True) == 0

    output = capsys.readouterr().out
    assert "fill_count=0" in output
    assert output.endswith("fills:\n")


def test_show_fills_does_not_change_backtest_summary_values(tmp_path, capsys) -> None:
    database = tmp_path / "same-result.db"
    _save_bars(
        database,
        ("3", "2", "1", "4", "0", "0", "1"),
        {4: "100", 6: "80"},
    )

    assert _run_backtest_cli(database, show_fills=False) == 0
    summary_only = capsys.readouterr().out
    assert _run_backtest_cli(database, show_fills=True) == 0
    with_fills = capsys.readouterr().out

    assert "fills:" not in summary_only
    for key in ("fill_count", "final_cash", "final_position_quantity", "final_portfolio_value"):
        assert _output_value(summary_only, key) == _output_value(with_fills, key)
