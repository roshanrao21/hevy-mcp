from contextvars import ContextVar

request_hevy_api_key: ContextVar[str | None] = ContextVar(
    "request_hevy_api_key", default=None
)
