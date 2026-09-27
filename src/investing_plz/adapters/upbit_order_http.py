from collections.abc import Callable
from decimal import Decimal
import json
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from investing_plz.adapters.upbit_auth import (
    UpbitAuthenticator,
    build_upbit_query_string,
)
from investing_plz.adapters.upbit_order import (
    UpbitOrderSnapshot,
    UpbitOrderValidationError,
    upbit_order_response_to_snapshot,
)


UPBIT_API_URL = "https://api.upbit.com/v1"


class UpbitPrivateApiError(RuntimeError):
    """A safe representation of an Upbit private API HTTP failure."""

    def __init__(
        self,
        *,
        status_code: int,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.error_message = error_message
        code = error_code or "unknown_error"
        message = error_message or "Upbit private API request failed"
        super().__init__(f"Upbit private API error {status_code} ({code}): {message}")


class UpbitPrivateAuthenticationError(UpbitPrivateApiError):
    """Upbit rejected authentication or API-key permissions."""


class UpbitPrivateRateLimitError(UpbitPrivateApiError):
    """Upbit rate-limited or temporarily blocked the caller."""


class UpbitPrivateTransportError(RuntimeError):
    """A private API request failed before a usable HTTP response arrived."""


class UpbitOrderStatusHttpSource:
    """Fetch one authenticated Upbit order snapshot by UUID."""

    def __init__(
        self,
        authenticator: UpbitAuthenticator,
        *,
        timeout: float = 10.0,
        base_url: str = UPBIT_API_URL,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        if not isinstance(authenticator, UpbitAuthenticator):
            raise TypeError("authenticator must be an UpbitAuthenticator")
        self._authenticator = authenticator
        self._timeout = timeout
        self._base_url = base_url.rstrip("/")
        self._opener = opener

    def __repr__(self) -> str:
        return f"{type(self).__name__}(authenticator=<redacted>)"

    def get_order(self, order_id: str) -> UpbitOrderSnapshot:
        if (
            not isinstance(order_id, str)
            or not order_id
            or order_id != order_id.strip()
        ):
            raise ValueError("order_id must be a non-empty unpadded string")

        parameters = [("uuid", order_id)]
        authentication_query = build_upbit_query_string(parameters)
        request_query = urlencode(parameters)
        request = Request(
            f"{self._base_url}/order?{request_query}",
            headers={
                "Authorization": self._authenticator.create_authorization_header(
                    query_string=authentication_query
                ),
                "Accept": "application/json",
                "User-Agent": "investing-plz/0.1",
            },
            method="GET",
        )
        payload = self._open_json(request)
        return upbit_order_response_to_snapshot(payload)

    def _open_json(self, request: Request) -> object:
        try:
            with self._opener(request, timeout=self._timeout) as response:
                payload_text = response.read().decode("utf-8")
        except HTTPError as error:
            error_code, error_message = _read_upbit_error(error)
            error_type: type[UpbitPrivateApiError]
            if error.code in (401, 403):
                error_type = UpbitPrivateAuthenticationError
            elif error.code in (418, 429):
                error_type = UpbitPrivateRateLimitError
            else:
                error_type = UpbitPrivateApiError
            raise error_type(
                status_code=error.code,
                error_code=error_code,
                error_message=error_message,
            ) from error
        except (TimeoutError, socket.timeout) as error:
            raise UpbitPrivateTransportError(
                "Upbit private API request timed out"
            ) from error
        except URLError as error:
            raise UpbitPrivateTransportError(
                "Upbit private API transport failed"
            ) from error

        try:
            return json.loads(
                payload_text,
                parse_float=Decimal,
                parse_constant=_reject_non_finite_json_number,
            )
        except (json.JSONDecodeError, ValueError) as error:
            raise UpbitOrderValidationError(
                "Upbit returned invalid order JSON"
            ) from error


def _read_upbit_error(error: HTTPError) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(error.read().decode("utf-8"))
        details = payload.get("error")
        if not isinstance(details, dict):
            return None, None
        code = details.get("name")
        message = details.get("message")
        return (
            code if isinstance(code, str) and code else None,
            message if isinstance(message, str) and message else None,
        )
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None, None


def _reject_non_finite_json_number(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")
