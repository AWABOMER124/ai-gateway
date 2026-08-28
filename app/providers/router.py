"""
Provider router — selects the best provider for a capability and handles fallback.

Selection order:
1. Find providers supporting the capability
2. Filter by enabled + circuit breaker availability
3. Sort by priority (lower = higher priority)
4. Try each in order; on retryable failure, fall back to next
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from app.core.context import ExecutionContext
from app.providers.health import circuit_breaker
from app.providers.models import ProviderResult, ProviderError, ProviderStatus
from app.providers.registry import provider_registry

logger = logging.getLogger(__name__)


class NoProviderAvailable(Exception):
    def __init__(self, capability: str, errors: list[ProviderError]):
        self.capability = capability
        self.errors = errors
        providers = ", ".join(e.provider for e in errors) if errors else "none registered"
        super().__init__(f"No provider available for '{capability}'. Tried: {providers}")


async def route(
    ctx: ExecutionContext,
    capability: str,
    params: dict[str, Any],
    timeout: Optional[float] = None,
) -> ProviderResult:
    """
    Route a capability request to the best available provider.
    Falls back through providers on retryable failures.
    """
    providers = provider_registry.find_by_capability(capability)
    if not providers:
        raise NoProviderAvailable(capability, [])

    providers.sort(key=lambda p: p.meta().priority)

    errors: list[ProviderError] = []

    for provider in providers:
        pk = provider.key

        if not circuit_breaker.is_available(pk):
            logger.debug("Circuit open for %s, skipping", pk)
            errors.append(ProviderError(
                provider=pk,
                capability=capability,
                status=ProviderStatus.ERROR,
                message="Circuit breaker open",
                retryable=True,
            ))
            continue

        start = time.monotonic()
        try:
            result = await provider.execute(
                capability=capability,
                params=params,
                timeout=timeout or provider.meta().timeout_seconds,
            )
            elapsed_ms = (time.monotonic() - start) * 1000
            result.elapsed_ms = int(elapsed_ms)

            if result.status == ProviderStatus.SUCCESS:
                circuit_breaker.record_success(pk, elapsed_ms)
                logger.info(
                    "Provider %s succeeded for %s in %dms",
                    pk, capability, int(elapsed_ms),
                )
                return result

            circuit_breaker.record_failure(pk, elapsed_ms)
            err = ProviderError(
                provider=pk,
                capability=capability,
                status=result.status,
                message=f"Provider returned {result.status.value}",
                http_status=result.http_status,
                elapsed_ms=int(elapsed_ms),
                retryable=result.status in (
                    ProviderStatus.TIMEOUT,
                    ProviderStatus.RATE_LIMITED,
                    ProviderStatus.ERROR,
                ),
            )
            errors.append(err)

            if not err.retryable:
                logger.warning("Non-retryable failure from %s: %s", pk, result.status)
                break

        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            circuit_breaker.record_failure(pk, elapsed_ms)
            logger.warning("Provider %s failed: %s", pk, e)
            errors.append(ProviderError(
                provider=pk,
                capability=capability,
                status=ProviderStatus.ERROR,
                message=str(e),
                elapsed_ms=int(elapsed_ms),
                retryable=True,
            ))

    raise NoProviderAvailable(capability, errors)
