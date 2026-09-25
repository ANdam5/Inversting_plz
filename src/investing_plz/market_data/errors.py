class MarketDataProviderError(RuntimeError):
    """Base error for failures while obtaining market data."""


class MarketDataTimeoutError(MarketDataProviderError):
    """The market-data provider did not respond before the timeout."""


class MarketDataRateLimitError(MarketDataProviderError):
    """The market-data provider rejected the request due to rate limiting."""

    def __init__(self, message: str, *, retry_after: str | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class MarketDataValidationError(MarketDataProviderError):
    """Provider data violates the normalized market-data contract."""

