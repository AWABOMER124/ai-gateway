"""
Tool policy enforcement — bridges the tool registry with the policy engine.

This module answers: "Can this actor execute this tool right now?"
It combines registry lookups, permission checks, and policy evaluation.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.core.context import ExecutionContext
from app.core.errors import (
    ToolPermissionDenied,
    ToolApprovalRequired,
    AICoreError,
    ErrorCode,
)
from app.core.policies import (
    PolicyDecision,
    check_tool_access,
)
from app.core.tenancy import get_tenant_config
from app.tools.registry import ToolDefinition, tool_registry

logger = logging.getLogger(__name__)


class ToolNotFound(AICoreError):
    def __init__(self, tool_key: str):
        super().__init__(
            ErrorCode.TOOL_NOT_FOUND,
            f"Tool not registered: {tool_key}",
            details={"tool": tool_key},
        )


class ToolDisabled(AICoreError):
    def __init__(self, tool_key: str):
        super().__init__(
            ErrorCode.TOOL_DISABLED,
            f"Tool is currently disabled: {tool_key}",
            details={"tool": tool_key},
        )


async def authorize_tool_call(
    ctx: ExecutionContext,
    tool_key: str,
) -> tuple[ToolDefinition, PolicyDecision]:
    """
    Full authorization pipeline for a tool call.

    Returns (tool_definition, policy_decision) on success.
    Raises on denial.

    Steps:
    1. Lookup in registry (reject unknown tools)
    2. Check enabled
    3. Check product scope
    4. Load tenant config for policy overrides
    5. Run full policy check (permission + risk × mode matrix)
    6. Return or raise based on decision
    """
    # 1. Registry lookup
    tool = tool_registry.get(tool_key)
    if tool is None:
        raise ToolNotFound(tool_key)

    # 2. Enabled check
    if not tool.enabled:
        raise ToolDisabled(tool_key)

    # 3. Product scope
    if not tool.is_available_for(ctx.product):
        raise ToolPermissionDenied(
            tool_key,
            f"Tool '{tool_key}' is not available for product '{ctx.product.value}'",
        )

    # 4. Tenant config for policy overrides
    tenant_policy = await get_tenant_config(ctx.tenant_id, ctx.product.value)

    # 5. Full policy check
    decision = check_tool_access(
        ctx=ctx,
        tool_key=tool_key,
        required_permission=_primary_permission(tool),
        risk_level=tool.risk_level,
        tool_enabled_for_tenant=True,  # Already checked in step 2
        tool_enabled_for_agent=_is_tool_enabled_for_agent(tool, ctx),
        tenant_policy=tenant_policy,
    )

    # 6. Act on decision
    if decision == PolicyDecision.DENIED:
        raise ToolPermissionDenied(tool_key)

    if decision == PolicyDecision.APPROVAL_REQUIRED:
        raise ToolApprovalRequired(tool_key)

    # ALLOW or DRAFT — caller handles DRAFT (saves output but doesn't execute side-effects)
    return tool, decision


def _primary_permission(tool: ToolDefinition) -> str:
    """Extract the primary required permission for policy check."""
    if tool.required_permissions:
        return tool.required_permissions[0]
    # Default: product.tool_key
    return f"{tool.product}.{tool.key}"


def _is_tool_enabled_for_agent(tool: ToolDefinition, ctx: ExecutionContext) -> bool:
    """Check if the tool is enabled for the agent in the current context."""
    if ctx.agent_id is None:
        return True  # Direct user call, not agent-mediated
    # Future: per-agent tool allow-lists
    return True
