import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from investing_plz.adapters.upbit import UpbitMarketDataProvider
from investing_plz.domain import Instrument

FIXTURE = Path(__file__).parent / "fixtures" / "upbit_day_candles.json"


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_upbit_fixture_is_converted_to_bar() -> None:
    payload = FIXTURE.read_bytes()
    opener = Mock(return_value=FakeResponse(payload))
    provider = UpbitMarketDataProvider(timeout=3.5, opener=opener)
    instrument = Instrument(venue="upbit", symbol="KRW-BTC")

    bars = provider.get_bars(instrument, "day")

    assert len(bars) == 1
    assert bars[0].instrument == instrument
    assert bars[0].timestamp == datetime(2026, 9, 24, tzinfo=timezone.utc)
    assert str(bars[0].close) == "161000000.0"

    request = opener.call_args.args[0]
    assert request.full_url == (
        "https://api.upbit.com/v1/candles/days?market=KRW-BTC&count=200"
    )
    assert opener.call_args.kwargs == {"timeout": 3.5}


def test_provider_returns_bars_in_time_order() -> None:
    candles = json.loads(FIXTURE.read_text(encoding="utf-8"))
    older = dict(candles[0], candle_date_time_utc="2026-09-23T00:00:00")
    payload = json.dumps([candles[0], older]).encode()
    provider = UpbitMarketDataProvider(opener=lambda *_args, **_kwargs: FakeResponse(payload))

    bars = provider.get_bars(Instrument("upbit", "KRW-BTC"), "day")

    assert bars[0].timestamp < bars[1].timestamp

