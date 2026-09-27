import json
from decimal import Decimal
from pathlib import Path

import pytest

from investing_plz.adapters.upbit_balance import (
    UpbitBalanceValidationError,
    upbit_account_to_balance,
    upbit_accounts_to_balances,
)


FIXTURE = Path(__file__).parent / "fixtures" / "upbit_accounts.json"


def account(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "currency": "BTC",
        "balance": "2.0",
        "locked": "0.0",
        "avg_buy_price": "140000000",
        "avg_buy_price_modified": False,
        "unit_currency": "KRW",
    }
    values.update(overrides)
    return values


def test_krw_and_btc_fixture_convert_to_provider_neutral_balances() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    balances = upbit_accounts_to_balances(payload)

    krw, btc = balances
    assert krw.asset == "KRW"
    assert krw.available == Decimal("1000000.0")
    assert krw.locked == Decimal("0.0")
    assert krw.total == Decimal("1000000.0")
    assert krw.average_buy_price == Decimal("0")
    assert krw.unit_currency == "KRW"
    assert btc.asset == "BTC"
    assert btc.available == Decimal("2.0")
    assert btc.average_buy_price == Decimal("140000000")
    assert btc.unit_currency == "KRW"


def test_multiple_balances_preserve_response_order() -> None:
    result = upbit_accounts_to_balances(
        [account(currency="ETH"), account(currency="BTC")]
    )

    assert tuple(balance.asset for balance in result) == ("ETH", "BTC")


def test_financial_string_precision_is_preserved() -> None:
    result = upbit_account_to_balance(
        account(balance="0.1234567890123456789")
    )

    assert result.available == Decimal("0.1234567890123456789")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("balance", 0.1),
        ("balance", None),
        ("balance", ""),
        ("balance", "NaN"),
        ("balance", "Infinity"),
        ("balance", "-1"),
        ("locked", 0.1),
        ("locked", None),
        ("locked", ""),
        ("locked", "NaN"),
        ("locked", "Infinity"),
        ("locked", "-1"),
        ("avg_buy_price", 0.1),
        ("avg_buy_price", None),
        ("avg_buy_price", ""),
        ("avg_buy_price", "NaN"),
        ("avg_buy_price", "Infinity"),
        ("avg_buy_price", "-1"),
    ],
)
def test_malformed_financial_fields_are_rejected(field: str, value: object) -> None:
    with pytest.raises(UpbitBalanceValidationError):
        upbit_account_to_balance(account(**{field: value}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("currency", ""),
        ("currency", " BTC"),
        ("unit_currency", ""),
        ("unit_currency", "KRW "),
    ],
)
def test_malformed_string_fields_are_rejected(field: str, value: str) -> None:
    with pytest.raises(UpbitBalanceValidationError):
        upbit_account_to_balance(account(**{field: value}))


@pytest.mark.parametrize("value", [0, 1, "false", None])
def test_avg_buy_price_modified_must_be_an_actual_bool(value: object) -> None:
    with pytest.raises(UpbitBalanceValidationError):
        upbit_account_to_balance(account(avg_buy_price_modified=value))


def test_missing_required_field_is_rejected() -> None:
    payload = account()
    del payload["locked"]

    with pytest.raises(UpbitBalanceValidationError):
        upbit_account_to_balance(payload)
