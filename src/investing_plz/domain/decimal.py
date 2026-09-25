from decimal import Decimal


def require_decimal(value: object, *, name: str) -> Decimal:
    """Require an exact Decimal for a financial value; floats are not accepted."""

    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal")
    return value

