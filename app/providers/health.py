"""
Circuit breaker and health monitoring for providers.

In-memory, per-process. No Redis dependency.
Tracks success/failure rates and implements CLOSED → OPEN → HALF_OPEN.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class ProviderHealth:
    """Health stats for a single provider."""
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    last_success: float = 0.0
    last_failure: float = 0.0
    total_latency_ms: float = 0.0
    state: CircuitState = CircuitState.CLOSED
    state_changed_at: float = field(default_factory=time.monotonic)

    @property
    def avg_latency_ms(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.total_latency_ms / total

    @property
    def failure_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.failure_count / total

    def to_dict(self) -> dict:
        return {
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "consecutive_failures": self.consecutive_failures,
            "failure_rate": round(self.failure_rate, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "state": self.state.value,
            "last_success": self.last_success,
            "last_failure": self.last_failure,
        }


class CircuitBreaker:
    """
    Simple deterministic circuit breaker.

    CLOSED: normal operation
    OPEN: provider is unhealthy, skip it (fallback to next)
    HALF_OPEN: allow one probe request to test recovery
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max: int = 1,
    ):
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max = half_open_max
        self._providers: dict[str, ProviderHealth] = {}
        self._lock = Lock()

    def _get(self, provider_key: str) -> ProviderHealth:
        if provider_key not in self._providers:
            self._providers[provider_key] = ProviderHealth()
        return self._providers[provider_key]

    def is_available(self, provider_key: str) -> bool:
        with self._lock:
            h = self._get(provider_key)
            now = time.monotonic()

            if h.state == CircuitState.CLOSED:
                return True

            if h.state == CircuitState.OPEN:
                if now - h.state_changed_at >= self._recovery_timeout:
                    h.state = CircuitState.HALF_OPEN
                    h.state_changed_at = now
                    return True
                return False

            return True

    def record_success(self, provider_key: str, latency_ms: float) -> None:
        with self._lock:
            h = self._get(provider_key)
            h.success_count += 1
            h.consecutive_failures = 0
            h.last_success = time.time()
            h.total_latency_ms += latency_ms

            if h.state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                h.state = CircuitState.CLOSED
                h.state_changed_at = time.monotonic()

    def record_failure(self, provider_key: str, latency_ms: float) -> None:
        with self._lock:
            h = self._get(provider_key)
            h.failure_count += 1
            h.consecutive_failures += 1
            h.last_failure = time.time()
            h.total_latency_ms += latency_ms

            if h.state == CircuitState.HALF_OPEN:
                h.state = CircuitState.OPEN
                h.state_changed_at = time.monotonic()
            elif (
                h.state == CircuitState.CLOSED
                and h.consecutive_failures >= self._failure_threshold
            ):
                h.state = CircuitState.OPEN
                h.state_changed_at = time.monotonic()

    def get_health(self, provider_key: str) -> ProviderHealth:
        with self._lock:
            return self._get(provider_key)

    def get_all_health(self) -> dict[str, ProviderHealth]:
        with self._lock:
            return dict(self._providers)

    def reset(self, provider_key: str) -> None:
        with self._lock:
            self._providers.pop(provider_key, None)


circuit_breaker = CircuitBreaker()
