from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class DatasetSummary:
    venue: str
    symbol: str
    timeframe: str
    row_count: int
    closed_bar_count: int
    earliest_timestamp: datetime | None
    latest_timestamp: datetime | None
    latest_closed_timestamp: datetime | None
    duplicate_count: int
    gap_count: int

