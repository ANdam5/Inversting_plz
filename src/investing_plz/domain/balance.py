from dataclasses import dataclass
from decimal import Decimal

from investing_plz.domain.decimal import require_decimal


@dataclass(frozen=True, slots=True)
class AssetBalance:
    """Provider-neutral available and locked amounts for one asset."""

    asset: str
    available: Decimal
    locked: Decimal
    average_buy_price: Decimal
    unit_currency: str

    def __post_init__(self) -> None:
        for name in ("asset", "unit_currency"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must not be empty")
            if value != value.strip():
                raise ValueError(f"{name} must not contain surrounding whitespace")

        for name in ("available", "locked", "average_buy_price"):
            value = require_decimal(getattr(self, name), name=name)
            if not value.is_finite():
                raise ValueError(f"{name} must be finite")
            if value < 0:
                raise ValueError(f"{name} must not be negative")

    @property
    def total(self) -> Decimal:
        return self.available + self.locked
