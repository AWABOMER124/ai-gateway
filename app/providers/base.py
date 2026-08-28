"""
Base provider contract — all provider adapters inherit from this.

A provider adapter translates between a normalized capability request
and a specific vendor API. It never exposes vendor-specific formats.
"""
from __future__ import annotations

import abc
from typing import Any, Optional

from app.providers.models import ProviderMeta, ProviderResult


class BaseProvider(abc.ABC):
    """Abstract base for all provider adapters."""

    @abc.abstractmethod
    def meta(self) -> ProviderMeta:
        """Return static metadata about this provider."""

    @abc.abstractmethod
    async def execute(
        self,
        capability: str,
        params: dict[str, Any],
        timeout: Optional[float] = None,
    ) -> ProviderResult:
        """Execute a capability request and return a normalized result."""

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """Quick check if the provider is reachable. Should not cost money."""

    @property
    def key(self) -> str:
        return self.meta().key

    @property
    def display_name(self) -> str:
        return self.meta().display_name

    def supports(self, capability: str) -> bool:
        return capability in self.meta().capabilities

    def is_enabled(self) -> bool:
        return self.meta().enabled
