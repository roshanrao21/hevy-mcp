class HevyMcpError(Exception):
    """Base application exception."""


class AuthenticationError(HevyMcpError):
    pass


class AuthorizationError(HevyMcpError):
    pass


class UpstreamError(HevyMcpError):
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
