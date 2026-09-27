from decimal import Decimal

import pytest

from investing_plz.domain import AssetBalance


def balance(**overrides: object) -> AssetBalance:
    values: dict[str, object] = {
        "asset": "BTC",
        "available": Decimal("1.25"),
        "locked": Decimal("0.75"),
        "average_buy_price": Decimal("140000000"),
        "unit_currency": "KRW",
    }
    values.update(overrides)
    return AssetBalance(**values)


def test_asset_balance_is_immutable_and_total_is_exact() -> None:
    result = balance()

    assert result.total == Decimal("2.00")
    with pytest.raises(AttributeError):
        result.available = Decimal("2")  # type: ignore[misc]


@pytest.mark.parametrize("field", ["available", "locked", "average_buy_price"])
def test_asset_balance_rejects_float_financial_values(field: str) -> None:
    with pytest.raises(TypeError, match="Decimal"):
        balance(**{field: 0.1})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("available", Decimal("-1")),
        ("locked", Decimal("-1")),
        ("average_buy_price", Decimal("-1")),
        ("available", Decimal("NaN")),
        ("locked", Decimal("Infinity")),
        ("average_buy_price", Decimal("-Infinity")),
    ],
)
def test_asset_balance_rejects_negative_or_non_finite_values(
    field: str, value: Decimal
) -> None:
    with pytest.raises(ValueError):
        balance(**{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("asset", ""),
        ("asset", " BTC"),
        ("asset", "BTC "),
        ("unit_currency", ""),
        ("unit_currency", " KRW"),
        ("unit_currency", "KRW "),
    ],
)
def test_asset_balance_rejects_empty_or_padded_codes(field: str, value: str) -> None:
    with pytest.raises(ValueError):
        balance(**{field: value})
