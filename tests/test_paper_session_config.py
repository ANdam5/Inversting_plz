import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from investing_plz.application import (
    PaperSessionConfigurationError,
    recover_paper_runtime,
)
from investing_plz.domain import Instrument, Order, OrderIntent, OrderSide
from investing_plz.storage import (
    PaperCursorScope,
    PaperSessionConfig,
    SQLitePaperRepository,
)


BTC = Instrument("upbit", "KRW-BTC")
ETH = Instrument("upbit", "KRW-ETH")
NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)


def config(**changes) -> PaperSessionConfig:
    values = {
        "instrument": BTC,
        "strategy_id": "moving_average_crossover",
        "timeframe": "day",
        "fast_window": 20,
        "slow_window": 60,
        "target_weight": Decimal("0.10"),
        "quantity_step": Decimal("0.00000001"),
        "min_trade_amount": Decimal("10000"),
        "initial_cash": Decimal("10000000"),
        "max_order_amount": Decimal("500000"),
        "max_instrument_weight": Decimal("0.20"),
        "min_cash_reserve": Decimal("1000000"),
        "fee_rate": Decimal("0.0005"),
        "slippage_bps": Decimal("5"),
    }
    values.update(changes)
    return PaperSessionConfig(**values)


def repository(path) -> SQLitePaperRepository:
    result = SQLitePaperRepository(path)
    result.initialize()
    return result


def recover(repo, requested: PaperSessionConfig):
    return recover_paper_runtime(
        repo,
        requested,
        order_id_factory=lambda: "new-order",
        submitted_at_factory=lambda: NOW,
    )


def test_empty_database_registers_config_and_recovers_from_durable_values(
    tmp_path,
) -> None:
    repo = repository(tmp_path / "paper.db")
    requested = config()

    recovered = recover(repo, requested)

    assert repo.get_session_config(requested.scope) == requested
    assert recovered.broker.initial_cash == requested.initial_cash
    assert recovered.broker.cash == requested.initial_cash


def test_config_round_trip_preserves_decimal_values_and_exponents(tmp_path) -> None:
    repo = repository(tmp_path / "paper.db")
    original = config(
        target_weight=Decimal("0.10"),
        quantity_step=Decimal("0.0000000100"),
        max_order_amount=Decimal("500000.00"),
    )

    assert repo.register_session_config(original) is True
    restored = repo.get_session_config(original.scope)

    assert restored == original
    assert restored is not None
    assert str(restored.target_weight) == "0.10"
    assert str(restored.quantity_step) == "1.00E-8"
    assert str(restored.max_order_amount) == "500000.00"
    assert repo.register_session_config(original) is False


@pytest.mark.parametrize(
    "changes",
    [
        {"initial_cash": Decimal("9000000")},
        {"fast_window": 15},
        {"slow_window": 80},
        {"target_weight": Decimal("0.20")},
        {"quantity_step": Decimal("0.0000001")},
        {"min_trade_amount": Decimal("5000")},
        {"max_order_amount": Decimal("400000")},
        {"max_instrument_weight": Decimal("0.30")},
        {"min_cash_reserve": Decimal("500000")},
        {"fee_rate": Decimal("0.001")},
        {"slippage_bps": Decimal("10")},
    ],
)
def test_same_scope_configuration_change_is_rejected(tmp_path, changes) -> None:
    repo = repository(tmp_path / "paper.db")
    original = config()
    repo.register_session_config(original)

    with pytest.raises(ValueError, match="configuration mismatch"):
        repo.register_session_config(replace(original, **changes))

    assert repo.get_session_config(original.scope) == original


@pytest.mark.parametrize(
    "changes",
    [
        {"instrument": ETH},
        {"strategy_id": "moving_average_crossover_v2"},
        {"timeframe": "minute60"},
    ],
)
def test_different_scope_config_is_rejected_by_singleton_db(tmp_path, changes) -> None:
    repo = repository(tmp_path / "paper.db")
    first = config()
    other = replace(first, **changes)

    assert repo.register_session_config(first)
    with pytest.raises(PaperSessionConfigurationError, match="different session"):
        repo.register_session_config(other)
    assert repo.get_session_config(first.scope) == first
    assert repo.get_session_config(other.scope) is None
    assert repo.list_session_configs() == (first,)


def test_repository_reopen_preserves_session_config(tmp_path) -> None:
    database = tmp_path / "paper.db"
    first = repository(database)
    expected = config()
    first.register_session_config(expected)

    second = repository(database)

    assert second.get_session_config(expected.scope) == expected


def test_legacy_database_with_multiple_configs_fails_closed(tmp_path) -> None:
    database = tmp_path / "paper.db"
    repo = repository(database)
    requested = config()
    repo.register_session_config(requested)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO paper_session_configs (
                venue, symbol, strategy_id, timeframe,
                fast_window, slow_window, target_weight,
                quantity_step, min_trade_amount, initial_cash,
                max_order_amount, max_instrument_weight,
                min_cash_reserve, fee_rate, slippage_bps
            )
            SELECT venue, 'KRW-ETH', strategy_id, timeframe,
                   fast_window, slow_window, target_weight,
                   quantity_step, min_trade_amount, '20000000',
                   max_order_amount, max_instrument_weight,
                   min_cash_reserve, fee_rate, slippage_bps
            FROM paper_session_configs
            """
        )

    with pytest.raises(PaperSessionConfigurationError, match="multiple"):
        recover(repo, requested)

    assert len(repo.list_session_configs()) == 2


def test_recovery_rejects_mismatch_without_mutating_durable_state(tmp_path) -> None:
    repo = repository(tmp_path / "paper.db")
    original = config()
    repo.register_session_config(original)
    cursor = datetime(2026, 9, 25, tzinfo=timezone.utc)
    repo.save_last_processed_bar_timestamp(original.scope, cursor)

    with pytest.raises(PaperSessionConfigurationError, match="does not match"):
        recover(repo, replace(original, initial_cash=Decimal("1")))

    assert repo.get_session_config(original.scope) == original
    assert repo.get_last_processed_bar_timestamp(original.scope) == cursor
    assert repo.list_orders() == ()
    assert repo.list_fills() == ()


def test_existing_state_without_config_fails_closed(tmp_path) -> None:
    repo = repository(tmp_path / "paper.db")
    requested = config()
    order = Order(
        order_id="legacy-order",
        instrument=ETH,
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        strategy_id="other-strategy",
        submitted_at=NOW,
    )
    repo.save_order(order)

    with pytest.raises(PaperSessionConfigurationError, match="without a session"):
        recover(repo, requested)

    assert repo.get_session_config(requested.scope) is None
    assert repo.get_order(order.order_id) == order


def test_recovery_uses_persisted_fee_and_slippage_without_separate_arguments(
    tmp_path,
) -> None:
    repo = repository(tmp_path / "paper.db")
    requested = config(initial_cash=Decimal("1000"))
    broker = recover(repo, requested).broker
    order = broker.submit(
        OrderIntent(
            requested.instrument,
            NOW,
            requested.strategy_id,
            OrderSide.BUY,
            Decimal("1"),
        )
    )

    fill = broker.execute_order(
        order.order_id,
        reference_price=Decimal("100"),
        fill_id="fill-1",
        filled_at=NOW,
    )

    assert fill is not None
    assert fill.fill_price == Decimal("100.05")
    assert fill.fee_amount == Decimal("0.050025")
    assert broker.cash == Decimal("899.899975")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"initial_cash": Decimal("0")}, "initial_cash"),
        ({"target_weight": 0.1}, "target_weight must be a Decimal"),
        ({"fee_rate": 0.0005}, "fee_rate must be a Decimal"),
        ({"slippage_bps": 5.0}, "slippage_bps must be a Decimal"),
        ({"fast_window": 60}, "smaller than"),
    ],
)
def test_session_config_reuses_existing_validation(changes, message) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        config(**changes)
