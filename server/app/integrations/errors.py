"""Stable, sanitized platform errors for client integration failures."""


class ClientGatewayError(RuntimeError):
    """Base error safe for conversion into an API response."""

    code = "CLIENT_ERROR"

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class ClientUnavailableError(ClientGatewayError):
    """Indicate that the client could not be reached or returned server errors."""

    code = "CLIENT_UNAVAILABLE"


class ClientTimeoutError(ClientGatewayError):
    """Indicate that a client request exceeded its configured deadline."""

    code = "CLIENT_TIMEOUT"


class ClientContractError(ClientGatewayError):
    """Indicate that a client response violated the integration contract."""

    code = "CLIENT_CONTRACT_ERROR"


class StaleClientContextError(ClientGatewayError):
    """Indicate that request versions no longer match authoritative state."""

    code = "STALE_CONTEXT"


class ClientAuthenticationError(ClientGatewayError):
    """Indicate that the client rejected integration credentials."""

    code = "CLIENT_AUTHENTICATION_ERROR"


class ClientRateLimitError(ClientGatewayError):
    """Indicate that the client temporarily rejected request volume."""

    code = "CLIENT_RATE_LIMITED"
