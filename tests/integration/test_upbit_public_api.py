import os

import pytest

from investing_plz.adapters.upbit import UpbitMarketDataProvider
from investing_plz.application.collect import collect_bars
from investing_plz.domain import Instrument
from investing_plz.storage import SQLiteBarStore


pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.getenv("RUN_UPBIT_INTEGRATION") != "1",
    reason="set RUN_UPBIT_INTEGRATION=1 to call the Upbit public API",
)
def test_collects_real_krw_btc_day_candles(tmp_path) -> None:
    result = collect_bars(
        UpbitMarketDataProvider(timeout=10.0),
        SQLiteBarStore(tmp_path / "upbit.db"),
        Instrument("upbit", "KRW-BTC"),
        "day",
    )

    assert result.fetched > 0
    assert result.inserted == result.fetched
    assert result.total == result.fetched
