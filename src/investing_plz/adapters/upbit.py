import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from investing_plz.domain import Bar, Instrument

UPBIT_API_URL = "https://api.upbit.com/v1"


def upbit_candle_to_bar(
    candle: dict[str, Any], instrument: Instrument, interval: str
) -> Bar:
    timestamp = datetime.fromisoformat(candle["candle_date_time_utc"]).replace(
        tzinfo=timezone.utc
    )
    return Bar(
        instrument=instrument,
        interval=interval,
        timestamp=timestamp,
        open=Decimal(str(candle["opening_price"])),
        high=Decimal(str(candle["high_price"])),
        low=Decimal(str(candle["low_price"])),
        close=Decimal(str(candle["trade_price"])),
        volume=Decimal(str(candle["candle_acc_trade_volume"])),
    )


class UpbitMarketDataProvider:
    """Upbit public candle API adapter."""

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        base_url: str = UPBIT_API_URL,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self._timeout = timeout
        self._base_url = base_url.rstrip("/")
        self._opener = opener

    def get_bars(self, instrument: Instrument, interval: str) -> Sequence[Bar]:
        if instrument.venue.lower() != "upbit":
            raise ValueError("Upbit provider requires an upbit instrument")
        if interval != "day":
            raise ValueError("only the day interval is supported in this slice")

        query = urlencode({"market": instrument.symbol, "count": 200})
        request = Request(
            f"{self._base_url}/candles/days?{query}",
            headers={"Accept": "application/json", "User-Agent": "investing-plz/0.1"},
        )
        with self._opener(request, timeout=self._timeout) as response:
            candles = json.loads(response.read().decode("utf-8"))

        bars = [upbit_candle_to_bar(item, instrument, interval) for item in candles]
        return sorted(bars, key=lambda bar: bar.timestamp)

