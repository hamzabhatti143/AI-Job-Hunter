"""rate_limiter_tool — Per-domain async rate limiter (token bucket).

Prevents IP bans from job boards by enforcing minimum delay between
requests to the same domain.

Usage:
    limiter = RateLimiter()
    await limiter.acquire("serpapi.com")   # blocks until safe to proceed
    response = await client.get(url)
"""
import asyncio
import time
from collections import defaultdict

# Minimum seconds between requests per domain
_DOMAIN_DELAYS: dict[str, float] = {
    "serpapi.com":              1.5,   # paid API — be polite
    "api.hunter.io":            1.0,
    "remoteok.com":             2.0,   # aggressive bot protection
    "remotive.com":             1.0,
    "weworkremotely.com":       1.5,
    "arbeitnow.com":            1.0,
    "findwork.dev":             1.0,
    "jobicy.com":               1.0,
    "themuse.com":              1.0,
    "nominatim.openstreetmap.org": 1.0,  # Nominatim rate limit: 1 req/sec
    "api.adzuna.com":           0.5,
}
_DEFAULT_DELAY = 0.5   # fallback for unlisted domains


class RateLimiter:
    """Shared async rate limiter. Use one instance per pipeline run."""

    def __init__(self):
        self._last: dict[str, float] = defaultdict(float)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _delay_for(self, domain: str) -> float:
        for pattern, delay in _DOMAIN_DELAYS.items():
            if pattern in domain:
                return delay
        return _DEFAULT_DELAY

    async def acquire(self, domain: str) -> None:
        """Wait until it is safe to make a request to this domain."""
        async with self._locks[domain]:
            now      = time.monotonic()
            delay    = self._delay_for(domain)
            elapsed  = now - self._last[domain]
            wait_for = delay - elapsed
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last[domain] = time.monotonic()


# Module-level singleton — shared across all tool calls in a process
_global_limiter = RateLimiter()


def get_limiter() -> RateLimiter:
    """Return the process-wide rate limiter instance."""
    return _global_limiter
