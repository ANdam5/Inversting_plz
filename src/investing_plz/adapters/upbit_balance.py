from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation

from investing_plz.domain import AssetBalance


class UpbitBalanceValidationError(ValueError):
    """An Upbit account payload violates the expected balance contract."""


def upbit_account_to_balance(account: Mapping[str, object]) -> AssetBalance:
    """Convert one Upbit account object without retaining provider metadata."""

    if not isinstance(account, Mapping):
        raise UpbitBalanceValidationError("Upbit account must be an object")
    try:
        modified = account["avg_buy_price_modified"]
        if type(modified) is not bool:
            raise TypeError("avg_buy_price_modified must be a bool")
        return AssetBalance(
            asset=_code(account["currency"], "currency"),
            available=_financial_decimal_string(account["balance"], "balance"),
            locked=_financial_decimal_string(account["locked"], "locked"),
            average_buy_price=_financial_decimal_string(
                account["avg_buy_price"], "avg_buy_price"
            ),
            unit_currency=_code(account["unit_currency"], "unit_currency"),
        )
    except (KeyError, TypeError, ValueError, InvalidOperation) as error:
        raise UpbitBalanceValidationError(f"invalid Upbit balance: {error}") from error


def upbit_accounts_to_balances(
    accounts: Sequence[Mapping[str, object]],
) -> tuple[AssetBalance, ...]:
    """Convert an Upbit accounts response while preserving response order."""

    if not isinstance(accounts, Sequence) or isinstance(accounts, (str, bytes)):
        raise UpbitBalanceValidationError("Upbit accounts response must be a sequence")
    return tuple(upbit_account_to_balance(account) for account in accounts)


def _financial_decimal_string(value: object, field: str) -> Decimal:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    if not value:
        raise ValueError(f"{field} must not be empty")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def _code(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field} must not contain surrounding whitespace")
    return value
