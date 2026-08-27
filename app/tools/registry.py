"""
Tool Registry — central catalog of all tools the AI can invoke.

Tools are registered with metadata including risk classification,
required permissions, product scope, and validation schemas.
The registry is the single source of truth for tool authorization.

Key invariants:
- Un-registered tool names are ALWAYS rejected
- Risk level is set at registration, never at call time
- Product scope restricts which products can use which tools
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

from app.core.context import ExecutionContext, Product
from app.core.policies import RiskLevel

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """Immutable definition of a registered tool."""
    key: str                          # Unique tool identifier: "product.category.action"
    version: str                      # Semantic version, e.g. "1.0.0"
    product: str                      # Owning product: "qiad", "wasla", "core", "*"
    description: str
    risk_level: RiskLevel
    required_permissions: list[str]   # All must be present on the actor
    input_schema: Optional[dict] = None   # JSON Schema for input validation
    output_schema: Optional[dict] = None  # JSON Schema for output validation
    approval_policy: Optional[str] = None  # Override default policy
    idempotency_required: bool = False
    timeout_seconds: int = 30
    enabled: bool = True
    handler: Optional[Callable[..., Coroutine]] = None

    # Products that can use this tool (empty = only owning product)
    allowed_products: list[str] = field(default_factory=list)

    def is_available_for(self, product: Product) -> bool:
        """Check if this tool is available for a given product."""
        if self.product == "*":
            return True
        if product.value == self.product:
            return True
        return product.value in self.allowed_products


class ToolRegistry:
    """
    In-memory registry of all tools the AI platform can invoke.

    Thread-safe for reads after startup registration is complete.
    Tools are registered at import time or during app startup.
    """

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition. Overwrites if same key exists."""
        if not tool.key:
            raise ValueError("Tool key cannot be empty")
        if tool.key in self._tools:
            logger.warning("Overwriting tool registration: %s", tool.key)
        self._tools[tool.key] = tool
        logger.info("Registered tool: %s (risk=%s)", tool.key, tool.risk_level.value)

    def get(self, key: str) -> Optional[ToolDefinition]:
        """Look up a tool by its key. Returns None if not registered."""
        return self._tools.get(key)

    def list_tools(
        self,
        product: Optional[Product] = None,
        risk_level: Optional[RiskLevel] = None,
        enabled_only: bool = True,
    ) -> list[ToolDefinition]:
        """List tools with optional filters."""
        tools = list(self._tools.values())
        if enabled_only:
            tools = [t for t in tools if t.enabled]
        if product:
            tools = [t for t in tools if t.is_available_for(product)]
        if risk_level:
            tools = [t for t in tools if t.risk_level == risk_level]
        return tools

    def list_tool_keys(self, product: Optional[Product] = None) -> list[str]:
        """List available tool keys for a product."""
        return [t.key for t in self.list_tools(product=product)]

    def is_registered(self, key: str) -> bool:
        return key in self._tools

    def disable(self, key: str) -> None:
        """Disable a tool at runtime (e.g. for incident response)."""
        tool = self._tools.get(key)
        if tool:
            self._tools[key] = ToolDefinition(
                **{**tool.__dict__, "enabled": False}
            )

    def enable(self, key: str) -> None:
        tool = self._tools.get(key)
        if tool:
            self._tools[key] = ToolDefinition(
                **{**tool.__dict__, "enabled": True}
            )


# Singleton registry — import and use throughout the application
tool_registry = ToolRegistry()


def register_tool(
    key: str,
    version: str = "1.0.0",
    product: str = "core",
    description: str = "",
    risk_level: RiskLevel = RiskLevel.READ_ONLY,
    required_permissions: Optional[list[str]] = None,
    input_schema: Optional[dict] = None,
    output_schema: Optional[dict] = None,
    idempotency_required: bool = False,
    timeout_seconds: int = 30,
    allowed_products: Optional[list[str]] = None,
):
    """Decorator to register a function as a tool handler."""
    def decorator(fn):
        tool = ToolDefinition(
            key=key,
            version=version,
            product=product,
            description=description,
            risk_level=risk_level,
            required_permissions=required_permissions or [],
            input_schema=input_schema,
            output_schema=output_schema,
            idempotency_required=idempotency_required,
            timeout_seconds=timeout_seconds,
            allowed_products=allowed_products or [],
            handler=fn,
        )
        tool_registry.register(tool)
        return fn
    return decorator
