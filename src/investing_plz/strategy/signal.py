from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from investing_plz.domain import Instrument
from investing_plz.domain.time import require_utc


class SignalType(StrEnum):
    BULLISH_CROSSOVER = "bullish_crossover"
    BEARISH_CROSSOVER = "bearish_crossover"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class Signal:
    instrument: Instrument
    timestamp: datetime
    signal_type: SignalType
    strategy_id: str

    def __post_init__(self) -> None:
        require_utc(self.timestamp)
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must not be empty")

