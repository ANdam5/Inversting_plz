from dataclasses import dataclass
from datetime import datetime

from investing_plz.domain.time import require_utc


@dataclass(frozen=True, slots=True)
class FixedClock:
    current: datetime

    def __post_init__(self) -> None:
        require_utc(self.current)

    def now(self) -> datetime:
        return self.current
