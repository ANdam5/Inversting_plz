import json
import socket
from datetime import datetime, timedelta, timezone
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import pytest

from investing_plz.adapters.upbit import UpbitMarketDataProvider
from investing_plz.domain import Instrument
from investing_plz.market_data import (
    MarketDataRateLimitError,
    MarketDataTimeoutError,
    MarketDataValidationError,
)
from investing_plz.market_data.validation import validate_bar_series
from tests.test_upbit_provider import FakeResponse


def candle(timestamp: datetime, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "candle_date_time_utc": timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
        "opening_price": 100,
        "high_price": 120,
        "low_price": 90,
        "trade_price": 110,
        "candle_acc_trade_volume": 1,
    }
    value.update(overrides)
    return value


def encoded(items: list[dict[str, object]]) -> FakeResponse:
    return FakeResponse(json.dumps(items).encode())


def test_paginates_without_boundary_duplicate_or_gap() -> None:
    newest = datetime(2026, 9, 24, tzinfo=timezone.utc)
    first = [candle(newest - timedelta(days=index)) for index in range(200)]
    second = [candle(newest - timedelta(days=index)) for index in range(200, 400)]
    requests = []
    responses = iter([encoded(first), encoded(second)])

    def opener(request, **_kwargs):
        requests.append(request)
        return next(responses)

    provider = UpbitMarketDataProvider(
        opener=opener, max_pages=2, request_interval=0, sleeper=lambda _: None
    )
    bars = provider.get_bars(Instrument("upbit", "KRW-BTC"), "day")

    assert len(bars) == 400
    assert len({bar.timestamp for bar in bars}) == 400
    validate_bar_series(bars, "day")
    second_query = parse_qs(urlparse(requests[1].full_url).query)
    assert second_query["to"] == [first[-1]["candle_date_time_utc"] + "Z"]


def test_rejects_duplicate_at_page_boundary() -> None:
    newest = datetime(2026, 9, 24, tzinfo=timezone.utc)
    first = [candle(newest - timedelta(days=index)) for index in range(200)]
    second = [first[-1], candle(newest - timedelta(days=200))]
    responses = iter([encoded(first), encoded(second)])
    provider = UpbitMarketDataProvider(
        opener=lambda *_args, **_kwargs: next(responses),
        max_pages=2,
        request_interval=0,
    )

    with pytest.raises(MarketDataValidationError, match="across pages"):
        provider.get_bars(Instrument("upbit", "KRW-BTC"), "day")


def test_gap_at_page_boundary_is_detected() -> None:
    newest = datetime(2026, 9, 24, tzinfo=timezone.utc)
    first = [candle(newest - timedelta(days=index)) for index in range(200)]
    second = [candle(newest - timedelta(days=index)) for index in range(201, 203)]
    responses = iter([encoded(first), encoded(second)])
    provider = UpbitMarketDataProvider(
        opener=lambda *_args, **_kwargs: next(responses),
        max_pages=2,
        request_interval=0,
    )

    bars = provider.get_bars(Instrument("upbit", "KRW-BTC"), "day")
    with pytest.raises(MarketDataValidationError, match="missing candle"):
        validate_bar_series(bars, "day")


def test_provider_stops_pagination_after_reaching_since() -> None:
    newest = datetime(2026, 9, 24, tzinfo=timezone.utc)
    page = [candle(newest - timedelta(days=index)) for index in range(200)]
    calls = 0

    def opener(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return encoded(page)

    provider = UpbitMarketDataProvider(opener=opener, max_pages=5)
    bars = provider.get_bars(
        Instrument("upbit", "KRW-BTC"),
        "day",
        since=newest - timedelta(days=2),
    )

    assert calls == 1
    assert [bar.timestamp for bar in bars] == [newest - timedelta(days=1), newest]


@pytest.mark.parametrize(
    "error",
    [TimeoutError(), socket.timeout(), URLError(socket.timeout())],
)
def test_timeout_is_converted_to_standard_error(error) -> None:
    def opener(*_args, **_kwargs):
        raise error

    provider = UpbitMarketDataProvider(opener=opener)
    with pytest.raises(MarketDataTimeoutError, match="timed out"):
        provider.get_bars(Instrument("upbit", "KRW-BTC"), "day")


def test_http_429_is_converted_without_retry() -> None:
    headers = Message()
    headers["Retry-After"] = "2"
    calls = 0

    def opener(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise HTTPError("url", 429, "rate limited", headers, None)

    provider = UpbitMarketDataProvider(opener=opener, max_pages=3)
    with pytest.raises(MarketDataRateLimitError) as captured:
        provider.get_bars(Instrument("upbit", "KRW-BTC"), "day")

    assert calls == 1
    assert captured.value.retry_after == "2"


@pytest.mark.parametrize(
    "overrides",
    [
        {"high_price": 80},
        {"low_price": 115},
        {"high_price": 80, "low_price": 90},
        {"opening_price": -1},
        {"candle_acc_trade_volume": -1},
    ],
)
def test_malformed_ohlcv_fails_clearly(overrides) -> None:
    payload = encoded([candle(datetime(2026, 9, 24, tzinfo=timezone.utc), **overrides)])
    provider = UpbitMarketDataProvider(opener=lambda *_args, **_kwargs: payload)

    with pytest.raises(MarketDataValidationError, match="invalid Upbit candle"):
        provider.get_bars(Instrument("upbit", "KRW-BTC"), "day")


@pytest.mark.parametrize("non_finite", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_json_financial_numbers_are_rejected(non_finite) -> None:
    candle_payload = encoded(
        [
            candle(
                datetime(2026, 9, 24, tzinfo=timezone.utc),
                trade_price=non_finite,
            )
        ]
    )
    ticker_payload = (
        f'[{{"market":"KRW-BTC","trade_price":{non_finite}}}]'.encode()
    )

    candle_provider = UpbitMarketDataProvider(
        opener=lambda *_args, **_kwargs: candle_payload
    )
    ticker_provider = UpbitMarketDataProvider(
        opener=lambda *_args, **_kwargs: FakeResponse(ticker_payload)
    )

    with pytest.raises(MarketDataValidationError):
        candle_provider.get_bars(Instrument("upbit", "KRW-BTC"), "day")
    with pytest.raises(MarketDataValidationError, match="invalid JSON"):
        ticker_provider.get_current_price(Instrument("upbit", "KRW-BTC"))


def test_duplicate_timestamp_in_page_fails_clearly() -> None:
    item = candle(datetime(2026, 9, 24, tzinfo=timezone.utc))
    provider = UpbitMarketDataProvider(
        opener=lambda *_args, **_kwargs: encoded([item, item])
    )
    with pytest.raises(MarketDataValidationError, match="duplicate"):
        provider.get_bars(Instrument("upbit", "KRW-BTC"), "day")


def test_unexpected_upbit_page_order_fails_clearly() -> None:
    older = candle(datetime(2026, 9, 23, tzinfo=timezone.utc))
    newer = candle(datetime(2026, 9, 24, tzinfo=timezone.utc))
    provider = UpbitMarketDataProvider(
        opener=lambda *_args, **_kwargs: encoded([older, newer])
    )
    with pytest.raises(MarketDataValidationError, match="descending"):
        provider.get_bars(Instrument("upbit", "KRW-BTC"), "day")
