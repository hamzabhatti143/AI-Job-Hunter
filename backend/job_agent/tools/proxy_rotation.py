"""proxy_rotation_tool — Rotate IP addresses during scraping.

Maintains a pool of proxies loaded from the PROXY_LIST env var.
Rotates on each domain per session to prevent IP bans from job boards.

PROXY_LIST format (comma-separated):
  http://user:pass@host:port,http://user:pass@host2:port2

Falls back to direct (no proxy) if pool is empty.
"""
import os
import random
from urllib.parse import urlparse
from agents import function_tool

_RAW = os.getenv("PROXY_LIST", "")
_POOL: list[str] = [p.strip() for p in _RAW.split(",") if p.strip()]

# Per-domain sticky proxy index for the current process lifetime
_sticky: dict[str, int] = {}


def _domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return url


def get_proxy(url: str = "", rotate: bool = False) -> dict | None:
    """
    Return an httpx-compatible proxy dict or None for direct connection.

    Args:
        url:    The target URL (used to assign a sticky proxy per domain).
        rotate: If True, force a different proxy from the current sticky one.
    """
    if not _POOL:
        return None  # No proxies configured — use direct

    domain = _domain_of(url) if url else "__default__"

    if rotate or domain not in _sticky:
        # Pick a random index, different from current if rotating
        current = _sticky.get(domain, -1)
        candidates = [i for i in range(len(_POOL)) if i != current]
        _sticky[domain] = random.choice(candidates) if candidates else random.randrange(len(_POOL))

    proxy_url = _POOL[_sticky[domain]]
    return {"http://": proxy_url, "https://": proxy_url}


def get_proxy_for_httpx(url: str = "", rotate: bool = False) -> str | None:
    """Return a single proxy URL string for httpx AsyncClient(proxies=...)."""
    if not _POOL:
        return None
    domain = _domain_of(url) if url else "__default__"
    if rotate or domain not in _sticky:
        current = _sticky.get(domain, -1)
        candidates = [i for i in range(len(_POOL)) if i != current]
        _sticky[domain] = random.choice(candidates) if candidates else random.randrange(len(_POOL))
    return _POOL[_sticky[domain]]


def pool_size() -> int:
    return len(_POOL)


async def proxy_rotation_impl(url: str = "", rotate: bool = False) -> str:
    """Return the proxy to use for the given URL."""
    import json
    proxy = get_proxy_for_httpx(url=url, rotate=rotate)
    return json.dumps({
        "proxy":     proxy,
        "pool_size": pool_size(),
        "direct":    proxy is None,
    })


@function_tool
async def proxy_rotation_tool(url: str = "", rotate: bool = False) -> str:
    """Get the proxy URL to use for a given target URL.

    Returns proxy=None when no proxies are configured (direct connection).
    rotate=True forces switching to a different proxy for this domain.
    Configure proxies via the PROXY_LIST environment variable.
    """
    return await proxy_rotation_impl(url=url, rotate=rotate)
