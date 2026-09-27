import hashlib
from decimal import Decimal
from uuid import UUID

import jwt
import pytest

from investing_plz.adapters.upbit_auth import (
    UpbitAuthenticator,
    build_upbit_query_string,
    hash_upbit_query_string,
)


ACCESS_KEY = "test-access-key"
SECRET_KEY = "test-secret-key-" * 5
NONCE = "00000000-0000-0000-0000-000000000001"


def decode_token(token: str) -> tuple[dict[str, object], dict[str, object]]:
    header = jwt.get_unverified_header(token)
    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS512"])
    return header, payload


def test_jwt_without_query_contains_required_payload_only() -> None:
    authenticator = UpbitAuthenticator(
        ACCESS_KEY,
        SECRET_KEY,
        nonce_factory=lambda: NONCE,
    )

    header, payload = decode_token(authenticator.create_token())

    assert header["alg"] == "HS512"
    assert payload == {"access_key": ACCESS_KEY, "nonce": NONCE}


def test_jwt_with_query_contains_sha512_hash() -> None:
    query_string = "market=KRW-BTC&limit=10"
    authenticator = UpbitAuthenticator(
        ACCESS_KEY,
        SECRET_KEY,
        nonce_factory=lambda: NONCE,
    )

    _, payload = decode_token(authenticator.create_token(query_string=query_string))

    assert payload["query_hash"] == hashlib.sha512(
        query_string.encode("utf-8")
    ).hexdigest()
    assert payload["query_hash_alg"] == "SHA512"


@pytest.mark.parametrize(
    ("parameters", "expected"),
    [
        (
            [("market", "KRW-BTC"), ("limit", 10)],
            "market=KRW-BTC&limit=10",
        ),
        (
            [
                ("market", "KRW-BTC"),
                ("states[]", "wait"),
                ("states[]", "watch"),
            ],
            "market=KRW-BTC&states[]=wait&states[]=watch",
        ),
        (
            [
                ("market", "KRW-BTC"),
                ("side", "bid"),
                ("volume", Decimal("0.01")),
                ("price", Decimal("100.0")),
                ("ord_type", "limit"),
            ],
            "market=KRW-BTC&side=bid&volume=0.01&price=100.0&ord_type=limit",
        ),
    ],
)
def test_query_string_preserves_parameter_order_and_array_keys(
    parameters: list[tuple[str, object]], expected: str
) -> None:
    assert build_upbit_query_string(parameters) == expected


def test_query_hash_uses_exact_utf8_query_string() -> None:
    query_string = "market=KRW-BTC&states[]=wait&states[]=watch"

    assert hash_upbit_query_string(query_string) == hashlib.sha512(
        query_string.encode("utf-8")
    ).hexdigest()


def test_nonce_factory_is_used_once_per_token_and_can_be_deterministic() -> None:
    nonces = iter(("nonce-1", "nonce-2"))
    authenticator = UpbitAuthenticator(
        ACCESS_KEY,
        SECRET_KEY,
        nonce_factory=lambda: next(nonces),
    )

    _, first = decode_token(authenticator.create_token())
    _, second = decode_token(authenticator.create_token())

    assert first["nonce"] == "nonce-1"
    assert second["nonce"] == "nonce-2"


def test_default_nonce_factory_creates_distinct_uuid_values() -> None:
    authenticator = UpbitAuthenticator(ACCESS_KEY, SECRET_KEY)

    _, first = decode_token(authenticator.create_token())
    _, second = decode_token(authenticator.create_token())

    assert first["nonce"] != second["nonce"]
    assert str(UUID(str(first["nonce"]))) == first["nonce"]
    assert str(UUID(str(second["nonce"]))) == second["nonce"]


def test_fixed_nonce_factory_produces_deterministic_token() -> None:
    authenticator = UpbitAuthenticator(
        ACCESS_KEY,
        SECRET_KEY,
        nonce_factory=lambda: NONCE,
    )

    assert authenticator.create_token() == authenticator.create_token()


def test_authorization_header_uses_bearer_token() -> None:
    authenticator = UpbitAuthenticator(
        ACCESS_KEY,
        SECRET_KEY,
        nonce_factory=lambda: NONCE,
    )

    value = authenticator.create_authorization_header()

    assert value.startswith("Bearer ")
    assert decode_token(value.removeprefix("Bearer "))[1]["nonce"] == NONCE


def test_secret_is_not_exposed_by_repr_or_payload() -> None:
    authenticator = UpbitAuthenticator(
        ACCESS_KEY,
        SECRET_KEY,
        nonce_factory=lambda: NONCE,
    )

    _, payload = decode_token(authenticator.create_token())

    assert SECRET_KEY not in repr(authenticator)
    assert SECRET_KEY not in str(payload)
    assert "secret_key" not in payload


@pytest.mark.parametrize(
    ("access_key", "secret_key"),
    [("", SECRET_KEY), (ACCESS_KEY, "")],
)
def test_empty_credentials_are_rejected(access_key: str, secret_key: str) -> None:
    with pytest.raises(ValueError, match="must not be empty") as error:
        UpbitAuthenticator(access_key, secret_key)

    assert SECRET_KEY not in str(error.value)
