import json
import socket
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from investing_plz.domain import Bar, Instrument
from investing_plz.market_data.errors import (
    MarketDataProviderError,
    MarketDataRateLimitError,
    MarketDataTimeoutError,
    MarketDataValidationError,
)

UPBIT_API_URL = "https://api.upbit.com/v1"


def upbit_candle_to_bar(
    candle: dict[str, Any], instrument: Instrument, interval: str
) -> Bar:
    try:
        timestamp = datetime.fromisoformat(candle["candle_date_time_utc"])
        if timestamp.tzinfo is not None:
            raise ValueError("Upbit UTC timestamp unexpectedly contains an offset")
        return Bar(
            instrument=instrument,
            interval=interval,
            timestamp=timestamp.replace(tzinfo=timezone.utc),
            open=Decimal(str(candle["opening_price"])),
            high=Decimal(str(candle["high_price"])),
            low=Decimal(str(candle["low_price"])),
            close=Decimal(str(candle["trade_price"])),
            volume=Decimal(str(candle["candle_acc_trade_volume"])),
        )
    except (KeyError, TypeError, ValueError, ArithmeticError) as error:
        raise MarketDataValidationError(f"invalid Upbit candle: {error}") from error


class UpbitMarketDataProvider:
    """Upbit public candle API adapter."""

    def __init__(
        self,
        *,
        timeout: float = 10.0,
        base_url: str = UPBIT_API_URL,
        opener: Callable[..., Any] = urlopen,
        max_pages: int = 1,
        request_interval: float = 0.12,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        if request_interval < 0:
            raise ValueError("request_interval must not be negative")
        self._timeout = timeout
        self._base_url = base_url.rstrip("/")
        self._opener = opener
        self._max_pages = max_pages
        self._request_interval = request_interval
        self._sleeper = sleeper

    def get_bars(
        self,
        instrument: Instrument,
        interval: str,
        *,
        since: datetime | None = None,
    ) -> Sequence[Bar]:
        if instrument.venue.lower() != "upbit":
            raise ValueError("Upbit provider requires an upbit instrument")
        if interval != "day":
            raise ValueError("only the day interval is supported in this slice")

        all_bars: list[Bar] = []
        cursor: datetime | None = None
        for page_number in range(self._max_pages):
            candles = self._request_page(instrument, cursor)
            if not candles:
                break

            page_bars = [
                upbit_candle_to_bar(item, instrument, interval) for item in candles
            ]
            _validate_upbit_page_order(page_bars)
            all_bars.extend(page_bars)

            oldest = page_bars[-1].timestamp
            if since is not None and oldest <= since:
                break
            if len(candles) < 200:
                break
            cursor = oldest
            if page_number + 1 < self._max_pages:
                self._sleeper(self._request_interval)

        timestamps = [bar.timestamp for bar in all_bars]
        if len(timestamps) != len(set(timestamps)):
            raise MarketDataValidationError("duplicate candle timestamp across pages")

        bars = [bar for bar in all_bars if since is None or bar.timestamp > since]
        return sorted(bars, key=lambda bar: bar.timestamp)

    def _request_page(
        self, instrument: Instrument, cursor: datetime | None
    ) -> list[dict[str, Any]]:
        parameters: dict[str, str | int] = {
            "market": instrument.symbol,
            "count": 200,
        }
        if cursor is not None:
            parameters["to"] = cursor.strftime("%Y-%m-%dT%H:%M:%SZ")
        query = urlencode(parameters)
        request = Request(
            f"{self._base_url}/candles/days?{query}",
            headers={"Accept": "application/json", "User-Agent": "investing-plz/0.1"},
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as error:
            if error.code == 429:
                raise MarketDataRateLimitError(
                    "Upbit rate limit exceeded",
                    retry_after=error.headers.get("Retry-After"),
                ) from error
            raise MarketDataProviderError(f"Upbit HTTP error: {error.code}") from error
        except (TimeoutError, socket.timeout) as error:
            raise MarketDataTimeoutError("Upbit request timed out") from error
        except URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                raise MarketDataTimeoutError("Upbit request timed out") from error
            raise MarketDataProviderError(f"Upbit request failed: {error.reason}") from error

        try:
            candles = json.loads(payload)
        except json.JSONDecodeError as error:
            raise MarketDataValidationError("Upbit returned invalid JSON") from error
        if not isinstance(candles, list):
            raise MarketDataValidationError("Upbit candle response must be a list")
        return candles


def _validate_upbit_page_order(bars: Sequence[Bar]) -> None:
    timestamps = [bar.timestamp for bar in bars]
    if len(timestamps) != len(set(timestamps)):
        raise MarketDataValidationError("duplicate candle timestamp in Upbit page")
    if timestamps != sorted(timestamps, reverse=True):
        raise MarketDataValidationError(
            "Upbit candle page must be in descending timestamp order"
        )
