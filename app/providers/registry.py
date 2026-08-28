"""
Provider registry — central catalog of all registered provider adapters.

Providers register at import/startup time. The router queries this registry
to find providers for a given capability.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """In-memory registry of provider adapters."""

    def __init__(self):
        self._providers: dict[str, BaseProvider] = {}

    def register(self, provider: BaseProvider) -> None:
        key = provider.key
        if key in self._providers:
            logger.warning("Overwriting provider: %s", key)
        self._providers[key] = provider
        meta = provider.meta()
        logger.info(
            "Registered provider: %s (%s) capabilities=%s",
            key, meta.display_name, meta.capabilities,
        )

    def get(self, key: str) -> Optional[BaseProvider]:
        return self._providers.get(key)

    def find_by_capability(self, capability: str) -> list[BaseProvider]:
        return [
            p for p in self._providers.values()
            if p.supports(capability) and p.is_enabled()
        ]

    def list_all(self) -> list[BaseProvider]:
        return list(self._providers.values())

    def disable(self, key: str) -> bool:
        p = self._providers.get(key)
        if p:
            p.meta().enabled = False
            return True
        return False

    def enable(self, key: str) -> bool:
        p = self._providers.get(key)
        if p:
            p.meta().enabled = True
            return True
        return False


provider_registry = ProviderRegistry()
