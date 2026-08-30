import pytest

from hevy_mcp.security import InMemoryRateLimiter, require_confirmation


def test_confirmation_is_exact():
    with pytest.raises(ValueError):
        require_confirmation("yes")
    require_confirmation("CONFIRM")


def test_rate_limiter_blocks_after_limit():
    limiter = InMemoryRateLimiter(requests=2, window_seconds=60)
    assert limiter.allow("caller")
    assert limiter.allow("caller")
    assert not limiter.allow("caller")
