from datetime import datetime
from typing import Protocol, Sequence

from investing_plz.domain import Bar, Instrument


class MarketDataProvider(Protocol):
    """Minimal source of normalized historical bars."""

    def get_bars(
        self,
        instrument: Instrument,
        interval: str,
        *,
        since: datetime | None = None,
    ) -> Sequence[Bar]: ...
