from collections.abc import Callable, Sequence
from decimal import Decimal
import hashlib
from typing import TypeAlias
from urllib.parse import unquote, urlencode
from uuid import uuid4

import jwt


UpbitParameterValue: TypeAlias = str | int | Decimal
UpbitParameters: TypeAlias = Sequence[tuple[str, UpbitParameterValue]]


def build_upbit_query_string(parameters: UpbitParameters) -> str:
    """Build the ordered, non-percent-encoded string required for Upbit auth."""

    normalized: list[tuple[str, str | int]] = []
    for key, value in parameters:
        if not isinstance(key, str) or not key:
            raise ValueError("parameter key must be a non-empty string")
        if not isinstance(value, (str, int, Decimal)) or isinstance(value, bool):
            raise TypeError("parameter value must be str, int, or Decimal")
        normalized.append((key, str(value) if isinstance(value, Decimal) else value))
    return unquote(urlencode(normalized, doseq=True))


def hash_upbit_query_string(query_string: str) -> str:
    if not isinstance(query_string, str):
        raise TypeError("query_string must be a string")
    return hashlib.sha512(query_string.encode("utf-8")).hexdigest()


def _uuid_nonce() -> str:
    return str(uuid4())


class UpbitAuthenticator:
    """Create Upbit HS512 JWTs without performing any HTTP requests."""

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        *,
        nonce_factory: Callable[[], str] = _uuid_nonce,
    ) -> None:
        if not isinstance(access_key, str) or not access_key:
            raise ValueError("access_key must not be empty")
        if not isinstance(secret_key, str) or not secret_key:
            raise ValueError("secret_key must not be empty")
        if not callable(nonce_factory):
            raise TypeError("nonce_factory must be callable")
        self._access_key = access_key
        self._secret_key = secret_key
        self._nonce_factory = nonce_factory

    def __repr__(self) -> str:
        return f"{type(self).__name__}(credentials=<redacted>)"

    def create_token(self, *, query_string: str | None = None) -> str:
        nonce = self._nonce_factory()
        if not isinstance(nonce, str) or not nonce:
            raise ValueError("nonce_factory must return a non-empty string")
        payload = {"access_key": self._access_key, "nonce": nonce}
        if query_string:
            payload["query_hash"] = hash_upbit_query_string(query_string)
            payload["query_hash_alg"] = "SHA512"
        return jwt.encode(payload, self._secret_key, algorithm="HS512")

    def create_authorization_header(self, *, query_string: str | None = None) -> str:
        return f"Bearer {self.create_token(query_string=query_string)}"
