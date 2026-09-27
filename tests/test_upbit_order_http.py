import hashlib
import io
import json
import socket
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import jwt
import pytest

from investing_plz.adapters.upbit_auth import UpbitAuthenticator
from investing_plz.adapters.upbit_order import UpbitOrderValidationError
from investing_plz.adapters.upbit_order_http import (
    UpbitOrderStatusHttpSource,
    UpbitPrivateApiError,
    UpbitPrivateAuthenticationError,
    UpbitPrivateRateLimitError,
    UpbitPrivateTransportError,
)
from investing_plz.adapters.upbit_order_tracker import UpbitOrderTracker


ACCESS_KEY = "fake-access-key"
SECRET_KEY = "fake-secret-key-" * 5
ORDER_ID = "order-uuid-1"


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def order_payload(
    *,
    state: str = "wait",
    executed: str = "0",
    remaining: str = "1",
    trades: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    trades = trades or []
    return {
        "uuid": ORDER_ID,
        "side": "bid",
        "ord_type": "limit",
        "price": "100",
        "state": state,
        "market": "KRW-BTC",
        "created_at": "2026-09-27T00:00:00Z",
        "volume": "1",
        "remaining_volume": remaining,
        "reserved_fee": "0.05",
        "remaining_fee": "0.05",
        "paid_fee": "0",
        "locked": "100.05",
        "executed_volume": executed,
        "trades_count": len(trades),
        "trades": trades,
    }


def trade(trade_id: str, volume: str, minute: int) -> dict[str, object]:
    return {
        "market": "KRW-BTC",
        "uuid": trade_id,
        "price": "100",
        "volume": volume,
        "funds": str(Decimal(volume) * Decimal("100")),
        "side": "bid",
        "created_at": f"2026-09-27T00:{minute:02d}:00Z",
    }


def make_source(opener, *, nonces=None) -> UpbitOrderStatusHttpSource:
    nonces = iter(nonces or ["nonce-1"])
    return UpbitOrderStatusHttpSource(
        UpbitAuthenticator(
            ACCESS_KEY,
            SECRET_KEY,
            nonce_factory=lambda: next(nonces),
        ),
        opener=opener,
        timeout=3.5,
    )


def test_authenticated_get_uses_matching_uuid_query_hash() -> None:
    requests = []

    def opener(request, *, timeout):
        requests.append((request, timeout))
        return FakeResponse(json.dumps(order_payload()).encode("utf-8"))

    snapshot = make_source(opener).get_order(ORDER_ID)

    request, timeout = requests[0]
    parsed = urlparse(request.full_url)
    authorization = request.get_header("Authorization")
    assert request.get_method() == "GET"
    assert parsed.path == "/v1/order"
    assert parse_qs(parsed.query) == {"uuid": [ORDER_ID]}
    assert request.get_header("Accept") == "application/json"
    assert request.get_header("User-agent") == "investing-plz/0.1"
    assert authorization.startswith("Bearer ")
    token = authorization.removeprefix("Bearer ")
    assert jwt.get_unverified_header(token)["alg"] == "HS512"
    decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS512"])
    assert decoded["access_key"] == ACCESS_KEY
    assert decoded["nonce"] == "nonce-1"
    assert decoded["query_hash"] == hashlib.sha512(
        f"uuid={ORDER_ID}".encode("utf-8")
    ).hexdigest()
    assert decoded["query_hash_alg"] == "SHA512"
    assert timeout == 3.5
    assert snapshot.uuid == ORDER_ID


def test_each_poll_creates_a_new_authorization_nonce() -> None:
    tokens: list[str] = []

    def opener(request, *, timeout):
        tokens.append(request.get_header("Authorization").removeprefix("Bearer "))
        return FakeResponse(json.dumps(order_payload()).encode("utf-8"))

    source = make_source(opener, nonces=["nonce-1", "nonce-2"])

    source.get_order(ORDER_ID)
    source.get_order(ORDER_ID)

    assert [
        jwt.decode(token, SECRET_KEY, algorithms=["HS512"])["nonce"]
        for token in tokens
    ] == ["nonce-1", "nonce-2"]
    assert tokens[0] != tokens[1]


def test_http_source_connects_to_tracker_without_network() -> None:
    trade_a = trade("trade-a", "0.4", 1)
    trade_b = trade("trade-b", "0.3", 2)
    trade_c = trade("trade-c", "0.3", 3)
    payloads = iter(
        [
            order_payload(),
            order_payload(executed="0.4", remaining="0.6", trades=[trade_a]),
            order_payload(
                executed="0.7", remaining="0.3", trades=[trade_a, trade_b]
            ),
            order_payload(
                state="done",
                executed="1",
                remaining="0",
                trades=[trade_a, trade_b, trade_c],
            ),
        ]
    )
    tokens: list[str] = []

    def opener(request, *, timeout):
        tokens.append(request.get_header("Authorization").removeprefix("Bearer "))
        return FakeResponse(json.dumps(next(payloads)).encode("utf-8"))

    source = make_source(
        opener,
        nonces=["nonce-1", "nonce-2", "nonce-3", "nonce-4"],
    )
    tracker = UpbitOrderTracker(ORDER_ID, source)

    progresses = [tracker.poll() for _ in range(4)]

    assert [
        tuple(item.trade_id for item in progress.newly_observed_trades)
        for progress in progresses
    ] == [(), ("trade-a",), ("trade-b",), ("trade-c",)]
    assert tracker.is_terminal
    assert [
        jwt.decode(token, SECRET_KEY, algorithms=["HS512"])["nonce"]
        for token in tokens
    ] == ["nonce-1", "nonce-2", "nonce-3", "nonce-4"]


@pytest.mark.parametrize("order_id", ["", "   ", " order-1", "order-1 "])
def test_order_id_must_be_non_empty_and_unpadded(order_id: str) -> None:
    source = make_source(lambda *_args, **_kwargs: None)

    with pytest.raises(ValueError, match="order_id"):
        source.get_order(order_id)


@pytest.mark.parametrize(
    ("status", "expected_type", "error_code"),
    [
        (401, UpbitPrivateAuthenticationError, "invalid_access_key"),
        (403, UpbitPrivateAuthenticationError, "out_of_scope"),
        (404, UpbitPrivateApiError, "order_not_found"),
        (429, UpbitPrivateRateLimitError, "too_many_requests"),
        (418, UpbitPrivateRateLimitError, "temporarily_blocked"),
        (500, UpbitPrivateApiError, "server_error"),
    ],
)
def test_private_http_errors_preserve_safe_status_and_upbit_error(
    status: int,
    expected_type: type[UpbitPrivateApiError],
    error_code: str,
) -> None:
    body = json.dumps(
        {"error": {"name": error_code, "message": "safe API message"}}
    ).encode("utf-8")

    def opener(request, *, timeout):
        raise HTTPError(
            request.full_url,
            status,
            "error",
            {},
            io.BytesIO(body),
        )

    with pytest.raises(expected_type) as raised:
        make_source(opener).get_order(ORDER_ID)

    assert raised.value.status_code == status
    assert raised.value.error_code == error_code
    assert raised.value.error_message == "safe API message"


@pytest.mark.parametrize(
    "failure",
    [TimeoutError(), socket.timeout(), URLError("offline")],
)
def test_transport_errors_are_mapped_without_request_secrets(failure: Exception) -> None:
    def opener(*_args, **_kwargs):
        raise failure

    with pytest.raises(UpbitPrivateTransportError) as raised:
        make_source(opener).get_order(ORDER_ID)

    message = str(raised.value)
    assert SECRET_KEY not in message
    assert "Bearer " not in message
    assert "eyJ" not in message


@pytest.mark.parametrize(
    "response",
    [b"not-json", json.dumps({"uuid": ORDER_ID}).encode("utf-8")],
)
def test_invalid_json_or_malformed_success_payload_is_validation_error(
    response: bytes,
) -> None:
    source = make_source(lambda *_args, **_kwargs: FakeResponse(response))

    with pytest.raises(UpbitOrderValidationError):
        source.get_order(ORDER_ID)


def test_source_repr_and_errors_do_not_expose_credentials_or_authorization() -> None:
    source = make_source(lambda *_args, **_kwargs: FakeResponse(b"not-json"))

    with pytest.raises(UpbitOrderValidationError) as raised:
        source.get_order(ORDER_ID)

    combined = repr(source) + str(raised.value)
    assert SECRET_KEY not in combined
    assert "Bearer " not in combined
    assert "eyJ" not in combined
