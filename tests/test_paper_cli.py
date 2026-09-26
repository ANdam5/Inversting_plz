from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from investing_plz.cli import build_parser, main
from investing_plz.clock import FixedClock
from investing_plz.domain import Bar, Instrument
from investing_plz.storage import PaperCursorScope, SQLitePaperRepository


NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)


class FakePublicProvider:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def get_bars(self, instrument, interval, *, since=None):
        start = datetime(2026, 9, 22, tzinfo=timezone.utc)
        return [
            Bar(
                instrument=instrument,
                interval=interval,
                timestamp=start + timedelta(days=index),
                open=Decimal(close),
                high=Decimal(close),
                low=Decimal(close),
                close=Decimal(close),
                volume=Decimal("1"),
            )
            for index, close in enumerate(("3", "2", "1", "4"))
        ]

    def get_current_price(self, instrument):
        return Decimal("100")


def paper_args(database, *, enabled=True):
    result = [
        "paper",
        "--venue", "upbit",
        "--symbol", "KRW-BTC",
        "--timeframe", "day",
        "--paper-database", str(database),
        "--fast", "2",
        "--slow", "3",
        "--initial-cash", "1000",
        "--target-weight", "0.5",
        "--quantity-step", "1",
        "--min-trade-amount", "0",
        "--max-order-amount", "1000",
        "--max-instrument-weight", "1",
        "--min-cash-reserve", "0",
        "--max-data-delay-seconds", "0",
        "--once",
    ]
    if enabled:
        result.append("--enable-trading")
    return result


def test_paper_cli_parses_financial_values_as_decimal(tmp_path) -> None:
    args = build_parser().parse_args(paper_args(tmp_path / "paper.db"))

    for name in (
        "initial_cash",
        "target_weight",
        "quantity_step",
        "min_trade_amount",
        "max_order_amount",
        "max_instrument_weight",
        "min_cash_reserve",
        "fee_rate",
        "slippage_bps",
    ):
        assert isinstance(getattr(args, name), Decimal)


def test_paper_cli_once_composes_fake_public_feed_end_to_end(tmp_path, capsys) -> None:
    database = tmp_path / "paper.db"
    with (
        patch("investing_plz.cli.UpbitMarketDataProvider", FakePublicProvider),
        patch("investing_plz.cli.SystemClock", return_value=FixedClock(NOW)),
        patch("investing_plz.cli.configure_structured_logging"),
    ):
        assert main(paper_args(database)) == 0

    output = capsys.readouterr().out
    repository = SQLitePaperRepository(database)
    scope = PaperCursorScope(
        Instrument("upbit", "KRW-BTC"), "moving_average_crossover", "day"
    )
    assert "session=new" in output
    assert "cash=500" in output
    assert "position_quantity=5" in output
    assert "reconciliation_safe=True" in output
    assert "trading_enabled=True" in output
    assert len(repository.list_orders()) == len(repository.list_fills()) == 1
    assert repository.list_orders()[0].order_id.startswith("paper-order-")
    assert repository.list_fills()[0].fill_id.startswith("paper-fill-")
    assert repository.get_last_processed_bar_timestamp(scope) is not None


def test_paper_cli_defaults_to_disabled_without_enable_flag(tmp_path, capsys) -> None:
    database = tmp_path / "disabled.db"
    with (
        patch("investing_plz.cli.UpbitMarketDataProvider", FakePublicProvider),
        patch("investing_plz.cli.SystemClock", return_value=FixedClock(NOW)),
        patch("investing_plz.cli.configure_structured_logging"),
    ):
        assert main(paper_args(database, enabled=False)) == 0

    output = capsys.readouterr().out
    repository = SQLitePaperRepository(database)
    assert "trading_enabled=False" in output
    assert repository.list_orders() == repository.list_fills() == ()
