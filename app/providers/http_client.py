"""
Shared HTTP client for provider adapters.

Uses httpx (already a project dependency). Provides a single async client
with sensible defaults for timeouts, retries, and connection pooling.
"""
from __future__ import annotations

import httpx
from typing import Optional


_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client. Lazy-initialized."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=10),
        )
    return _client


async def close_http_client() -> None:
    """Close the shared client. Call on app shutdown."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None
