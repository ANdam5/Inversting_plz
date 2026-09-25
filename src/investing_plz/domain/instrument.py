from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Instrument:
    """A market instrument identified by its venue and venue symbol."""

    venue: str
    symbol: str

    def __post_init__(self) -> None:
        if not self.venue.strip():
            raise ValueError("venue must not be empty")
        if not self.symbol.strip():
            raise ValueError("symbol must not be empty")

