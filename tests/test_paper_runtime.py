from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from investing_plz.application import (
    PaperSessionConfigurationError,
    PaperTradingNotReadyError,
    run_paper_runtime,
)
from investing_plz.broker import PaperBroker
from investing_plz.clock import FixedClock
from investing_plz.domain import Bar, Instrument, OrderIntent, OrderSide
from investing_plz.market_data import MarketDataProviderError
from investing_plz.storage import PaperDecisionKey, PaperSessionConfig, SQLitePaperRepository


BTC = Instrument("upbit", "KRW-BTC")
START = datetime(2026, 9, 22, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)


class FakeMarketData:
    def __init__(self, bars, price=Decimal("100")) -> None:
        self.bars = bars
        self.price = price
        self.bar_calls = 0
        self.price_calls = 0

    def get_bars(self, instrument, interval, *, since=None):
        self.bar_calls += 1
        return self.bars

    def get_current_price(self, instrument):
        self.price_calls += 1
        return self.price


def bars(*closes: str) -> list[Bar]:
    return [
        Bar(
            instrument=BTC,
            interval="day",
            timestamp=START + timedelta(days=index),
            open=Decimal(text),
            high=Decimal(text),
            low=Decimal(text),
            close=Decimal(text),
            volume=Decimal("1"),
        )
        for index, text in enumerate(closes)
    ]


def config(**changes) -> PaperSessionConfig:
    values = {
        "instrument": BTC,
        "strategy_id": "moving_average_crossover",
        "timeframe": "day",
        "fast_window": 2,
        "slow_window": 3,
        "target_weight": Decimal("0.5"),
        "quantity_step": Decimal("1"),
        "min_trade_amount": Decimal("0"),
        "initial_cash": Decimal("1000"),
        "max_order_amount": Decimal("1000"),
        "max_instrument_weight": Decimal("1"),
        "min_cash_reserve": Decimal("0"),
        "fee_rate": Decimal("0"),
        "slippage_bps": Decimal("0"),
    }
    values.update(changes)
    return PaperSessionConfig(**values)


def run_once(
    repository,
    market_data,
    *,
    requested=None,
    now=NOW,
    enabled=True,
    order_ids=None,
    fill_ids=None,
    correlations=None,
    max_delay=timedelta(0),
):
    order_ids = order_ids if order_ids is not None else ["order-1"]
    fill_ids = fill_ids if fill_ids is not None else ["fill-1"]
    correlations = correlations if correlations is not None else ["correlation-1"]
    clock = FixedClock(now)
    return run_paper_runtime(
        requested or config(),
        repository=repository,
        market_data=market_data,
        clock=clock,
        poll_interval=timedelta(minutes=1),
        max_data_delay=max_delay,
        trading_enabled=enabled,
        once=True,
        order_id_factory=lambda: order_ids.pop(0),
        fill_id_factory=lambda: fill_ids.pop(0),
        correlation_id_factory=lambda: correlations.pop(0),
        submitted_at_factory=clock.now,
    )


def test_first_run_e2e_registers_executes_and_persists(tmp_path) -> None:
    repository = SQLitePaperRepository(tmp_path / "paper.db")
    result = run_once(repository, FakeMarketData(bars("3", "2", "1", "4")))

    assert result.session_created
    assert result.poll_result is not None and result.poll_result.processed
    assert repository.get_session_config(config().scope) == config()
    assert len(repository.list_orders()) == 1
    assert len(repository.list_fills()) == 1
    assert result.cash == Decimal("500")
    assert result.position_quantity == Decimal("5")
    assert repository.get_last_processed_bar_timestamp(config().scope) == START + timedelta(days=3)


def test_restart_recovers_and_same_bar_consumes_no_ids(tmp_path) -> None:
    database = tmp_path / "paper.db"
    first = run_once(
        SQLitePaperRepository(database), FakeMarketData(bars("3", "2", "1", "4"))
    )
    order_ids = ["unused-order"]
    fill_ids = ["unused-fill"]
    correlations = ["unused-correlation"]
    repository = SQLitePaperRepository(database)

    second = run_once(
        repository,
        FakeMarketData(bars("3", "2", "1", "4")),
        order_ids=order_ids,
        fill_ids=fill_ids,
        correlations=correlations,
    )

    assert not second.session_created
    assert second.cash == first.cash
    assert second.position_quantity == first.position_quantity
    assert len(repository.list_orders()) == len(repository.list_fills()) == 1
    assert order_ids == ["unused-order"]
    assert fill_ids == ["unused-fill"]
    assert correlations == ["unused-correlation"]


def test_restart_processes_only_latest_new_bar_once(tmp_path) -> None:
    database = tmp_path / "paper.db"
    run_once(SQLitePaperRepository(database), FakeMarketData(bars("3", "2", "1", "4")))
    repository = SQLitePaperRepository(database)

    result = run_once(
        repository,
        FakeMarketData(bars("3", "2", "1", "4", "5")),
        now=NOW + timedelta(days=1),
        correlations=["c-2"],
    )

    assert result.poll_result is not None and result.poll_result.processed
    assert result.last_processed_bar_timestamp == START + timedelta(days=4)
    assert len(repository.list_orders()) == 1


def test_disabled_and_stale_runs_do_not_read_price_or_advance_cursor(tmp_path) -> None:
    disabled_repo = SQLitePaperRepository(tmp_path / "disabled.db")
    disabled_market = FakeMarketData(bars("3", "2", "1", "4"))
    disabled = run_once(disabled_repo, disabled_market, enabled=False)
    stale_repo = SQLitePaperRepository(tmp_path / "stale.db")
    stale_market = FakeMarketData(bars("3", "2", "1", "4"))
    stale = run_once(
        stale_repo,
        stale_market,
        now=NOW + timedelta(days=1, hours=1),
        max_delay=timedelta(minutes=30),
    )

    for result, repository, market in (
        (disabled, disabled_repo, disabled_market),
        (stale, stale_repo, stale_market),
    ):
        assert result.poll_result is not None and not result.poll_result.processed
        assert repository.list_orders() == repository.list_fills() == ()
        assert repository.get_last_processed_bar_timestamp(config().scope) is None
        assert market.price_calls == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"instrument": Instrument("upbit", "KRW-ETH")},
        {"strategy_id": "other-strategy"},
        {"timeframe": "minute60"},
        {"fee_rate": Decimal("0.001")},
    ],
)
def test_configuration_mismatch_fails_before_market_data_or_mutation(
    tmp_path, changes
) -> None:
    database = tmp_path / "paper.db"
    repository = SQLitePaperRepository(database)
    run_once(repository, FakeMarketData(bars("3", "2", "1", "4")))
    before = (
        repository.list_orders(),
        repository.list_fills(),
        repository.get_last_processed_bar_timestamp(config().scope),
    )
    market = FakeMarketData(bars("3", "2", "1", "4"))

    with pytest.raises(PaperSessionConfigurationError):
        run_once(
            SQLitePaperRepository(database),
            market,
            requested=config(**changes),
        )

    reopened = SQLitePaperRepository(database)
    assert market.bar_calls == market.price_calls == 0
    assert (
        reopened.list_orders(),
        reopened.list_fills(),
        reopened.get_last_processed_bar_timestamp(config().scope),
    ) == before


def test_pending_reconciliation_blocks_before_market_data(tmp_path) -> None:
    repository = SQLitePaperRepository(tmp_path / "paper.db")
    repository.initialize()
    requested = config()
    repository.register_session_config(requested)
    broker = PaperBroker(
        initial_cash=requested.initial_cash,
        order_id_factory=lambda: "pending-order",
        submitted_at_factory=lambda: NOW,
    )
    pending = broker.submit(
        OrderIntent(BTC, NOW, requested.strategy_id, OrderSide.BUY, Decimal("1"))
    )
    repository.register_order_submission(
        PaperDecisionKey(requested.scope, START), pending
    )
    market = FakeMarketData(bars("3", "2", "1", "4"))

    with pytest.raises(PaperTradingNotReadyError):
        run_once(repository, market)

    assert market.bar_calls == market.price_calls == 0
    assert repository.list_fills() == ()


def test_network_failure_does_not_advance_cursor_or_create_orders(tmp_path) -> None:
    class FailingMarket(FakeMarketData):
        def get_bars(self, instrument, interval, *, since=None):
            raise MarketDataProviderError("offline")

    repository = SQLitePaperRepository(tmp_path / "paper.db")
    with pytest.raises(MarketDataProviderError, match="offline"):
        run_once(repository, FailingMarket([]))

    assert repository.list_orders() == repository.list_fills() == ()
    assert repository.get_last_processed_bar_timestamp(config().scope) is None


def test_continuous_runtime_retries_network_failure_and_stops_gracefully(
    tmp_path,
) -> None:
    class FlakyMarket(FakeMarketData):
        def get_bars(self, instrument, interval, *, since=None):
            self.bar_calls += 1
            if self.bar_calls == 1:
                raise MarketDataProviderError("temporary outage")
            return self.bars

    repository = SQLitePaperRepository(tmp_path / "paper.db")
    market = FlakyMarket(bars("3", "2", "1", "4"))
    sleep_calls = 0

    class MutableRuntimeClock:
        def __init__(self) -> None:
            self.current = NOW

        def now(self):
            return self.current

    clock = MutableRuntimeClock()

    def advance_and_stop(seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        clock.current += timedelta(minutes=1)
        if sleep_calls == 2:
            raise KeyboardInterrupt

    result = run_paper_runtime(
        config(),
        repository=repository,
        market_data=market,
        clock=clock,
        poll_interval=timedelta(minutes=1),
        max_data_delay=timedelta(minutes=1),
        trading_enabled=True,
        once=False,
        order_id_factory=lambda: "order-1",
        fill_id_factory=lambda: "fill-1",
        correlation_id_factory=lambda: "correlation-1",
        submitted_at_factory=clock.now,
        sleeper=advance_and_stop,
    )

    assert market.bar_calls == 2
    assert result.poll_result is not None and result.poll_result.processed
    assert len(repository.list_orders()) == len(repository.list_fills()) == 1
