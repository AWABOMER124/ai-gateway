"""
Risk classification and policy engine for tool execution.

Every tool has a risk level. The policy engine decides whether a tool call
can proceed autonomously, needs approval, or is denied — based on:
1. Tool risk level
2. Agent mode (off/copilot/assisted/autopilot)
3. Tenant policy overrides
4. Actor permissions
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from app.core.context import ExecutionContext, AgentMode


class RiskLevel(str, Enum):
    READ_ONLY = "read_only"
    LOW_RISK_WRITE = "low_risk_write"
    EXTERNAL_COMMUNICATION = "external_communication"
    SENSITIVE_WRITE = "sensitive_write"
    FINANCIAL = "financial"
    DESTRUCTIVE = "destructive"


class PolicyDecision(str, Enum):
    ALLOW = "allow"                    # Execute immediately
    DRAFT = "draft"                    # Save as draft only (copilot mode)
    APPROVAL_REQUIRED = "approval_required"  # Needs human approval
    DENIED = "denied"                  # Not allowed at all


# Default policy matrix: (risk_level, agent_mode) → decision
# This can be overridden per-tenant via ai_tenant_products.config
_DEFAULT_POLICY: dict[tuple[RiskLevel, AgentMode], PolicyDecision] = {
    # READ_ONLY — always allowed regardless of mode (except OFF)
    (RiskLevel.READ_ONLY, AgentMode.OFF): PolicyDecision.DENIED,
    (RiskLevel.READ_ONLY, AgentMode.COPILOT): PolicyDecision.ALLOW,
    (RiskLevel.READ_ONLY, AgentMode.ASSISTED): PolicyDecision.ALLOW,
    (RiskLevel.READ_ONLY, AgentMode.AUTOPILOT): PolicyDecision.ALLOW,

    # LOW_RISK_WRITE
    (RiskLevel.LOW_RISK_WRITE, AgentMode.OFF): PolicyDecision.DENIED,
    (RiskLevel.LOW_RISK_WRITE, AgentMode.COPILOT): PolicyDecision.DRAFT,
    (RiskLevel.LOW_RISK_WRITE, AgentMode.ASSISTED): PolicyDecision.ALLOW,
    (RiskLevel.LOW_RISK_WRITE, AgentMode.AUTOPILOT): PolicyDecision.ALLOW,

    # EXTERNAL_COMMUNICATION
    (RiskLevel.EXTERNAL_COMMUNICATION, AgentMode.OFF): PolicyDecision.DENIED,
    (RiskLevel.EXTERNAL_COMMUNICATION, AgentMode.COPILOT): PolicyDecision.DRAFT,
    (RiskLevel.EXTERNAL_COMMUNICATION, AgentMode.ASSISTED): PolicyDecision.APPROVAL_REQUIRED,
    (RiskLevel.EXTERNAL_COMMUNICATION, AgentMode.AUTOPILOT): PolicyDecision.ALLOW,

    # SENSITIVE_WRITE
    (RiskLevel.SENSITIVE_WRITE, AgentMode.OFF): PolicyDecision.DENIED,
    (RiskLevel.SENSITIVE_WRITE, AgentMode.COPILOT): PolicyDecision.DRAFT,
    (RiskLevel.SENSITIVE_WRITE, AgentMode.ASSISTED): PolicyDecision.APPROVAL_REQUIRED,
    (RiskLevel.SENSITIVE_WRITE, AgentMode.AUTOPILOT): PolicyDecision.APPROVAL_REQUIRED,

    # FINANCIAL — always requires approval in Phase 1
    (RiskLevel.FINANCIAL, AgentMode.OFF): PolicyDecision.DENIED,
    (RiskLevel.FINANCIAL, AgentMode.COPILOT): PolicyDecision.DRAFT,
    (RiskLevel.FINANCIAL, AgentMode.ASSISTED): PolicyDecision.APPROVAL_REQUIRED,
    (RiskLevel.FINANCIAL, AgentMode.AUTOPILOT): PolicyDecision.APPROVAL_REQUIRED,

    # DESTRUCTIVE — always requires approval
    (RiskLevel.DESTRUCTIVE, AgentMode.OFF): PolicyDecision.DENIED,
    (RiskLevel.DESTRUCTIVE, AgentMode.COPILOT): PolicyDecision.DENIED,
    (RiskLevel.DESTRUCTIVE, AgentMode.ASSISTED): PolicyDecision.APPROVAL_REQUIRED,
    (RiskLevel.DESTRUCTIVE, AgentMode.AUTOPILOT): PolicyDecision.APPROVAL_REQUIRED,
}


def evaluate_policy(
    risk_level: RiskLevel,
    ctx: ExecutionContext,
    tool_key: Optional[str] = None,
    tenant_policy: Optional[dict] = None,
) -> PolicyDecision:
    """
    Evaluate whether a tool call should proceed.

    Order of checks:
    1. Agent mode OFF → DENIED
    2. Tenant-specific policy override (if exists)
    3. Default policy matrix
    """
    if ctx.agent_mode == AgentMode.OFF:
        return PolicyDecision.DENIED

    # Tenant-level override (from ai_tenant_products.config.policies)
    if tenant_policy and tool_key:
        tool_overrides = tenant_policy.get("tool_overrides", {})
        if tool_key in tool_overrides:
            override = tool_overrides[tool_key]
            decision_str = override.get(ctx.agent_mode.value)
            if decision_str:
                try:
                    return PolicyDecision(decision_str)
                except ValueError:
                    pass  # Fall through to default

    # Default matrix
    key = (risk_level, ctx.agent_mode)
    return _DEFAULT_POLICY.get(key, PolicyDecision.APPROVAL_REQUIRED)


def check_permission(ctx: ExecutionContext, required_permission: str) -> bool:
    """Check if the actor has the required permission."""
    if "*" in ctx.actor.permissions:
        return True
    return required_permission in ctx.actor.permissions


def check_tool_access(
    ctx: ExecutionContext,
    tool_key: str,
    required_permission: str,
    risk_level: RiskLevel,
    tool_enabled_for_tenant: bool = True,
    tool_enabled_for_agent: bool = True,
    tenant_policy: Optional[dict] = None,
) -> PolicyDecision:
    """
    Full tool access check pipeline (Section 13 of the spec):
    1. Is tool enabled for tenant?
    2. Is tool enabled for agent?
    3. Does actor/agent have permission?
    4. Policy decision
    """
    if not tool_enabled_for_tenant:
        return PolicyDecision.DENIED

    if not tool_enabled_for_agent:
        return PolicyDecision.DENIED

    if not check_permission(ctx, required_permission):
        return PolicyDecision.DENIED

    return evaluate_policy(risk_level, ctx, tool_key, tenant_policy)
