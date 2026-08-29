"""TTL cache for provider results — in-memory, per-process."""
from __future__ import annotations

import hashlib
import json
import time
import logging
from dataclasses import dataclass
from threading import Lock
from typing import Optional

from app.providers.models import ProviderResult

logger = logging.getLogger(__name__)

_DEFAULT_TTLS: dict[str, int] = {
    "geo.geocode": 86400,
    "geo.reverse_geocode": 86400,
    "currency.convert": 3600,
    "weather.current": 900,
    "weather.forecast": 1800,
}


def _cache_key(capability: str, params: dict) -> str:
    raw = json.dumps({"c": capability, "p": params}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


@dataclass
class _CacheEntry:
    result: ProviderResult
    expires_at: float


class ProviderCache:
    def __init__(self, max_entries: int = 2000):
        self._store: dict[str, _CacheEntry] = {}
        self._lock = Lock()
        self._max = max_entries

    def get(self, capability: str, params: dict) -> Optional[ProviderResult]:
        key = _cache_key(capability, params)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.monotonic() > entry.expires_at:
                del self._store[key]
                return None
            result = entry.result
            result.cached = True
            return result

    def put(self, capability: str, params: dict, result: ProviderResult, ttl: Optional[int] = None) -> None:
        if ttl is None:
            ttl = _DEFAULT_TTLS.get(capability, 300)
        key = _cache_key(capability, params)
        with self._lock:
            if len(self._store) >= self._max:
                self._evict_expired()
            if len(self._store) >= self._max:
                oldest_key = next(iter(self._store))
                del self._store[oldest_key]
            self._store[key] = _CacheEntry(result=result, expires_at=time.monotonic() + ttl)

    def invalidate(self, capability: str, params: dict) -> bool:
        key = _cache_key(capability, params)
        with self._lock:
            return self._store.pop(key, None) is not None

    def clear(self) -> int:
        with self._lock:
            count = len(self._store)
            self._store.clear()
            return count

    def stats(self) -> dict:
        with self._lock:
            now = time.monotonic()
            total = len(self._store)
            expired = sum(1 for e in self._store.values() if now > e.expires_at)
            return {"total_entries": total, "expired": expired, "active": total - expired}

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, v in self._store.items() if now > v.expires_at]
        for k in expired:
            del self._store[k]


provider_cache = ProviderCache()
