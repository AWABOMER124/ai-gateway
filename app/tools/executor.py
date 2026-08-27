"""
Safe tool execution — the single path through which all AI tool calls run.

Responsibilities:
1. Authorization (via tool policy)
2. Input validation
3. Execution with timeout
4. Audit logging
5. Error standardization
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from app.core.context import ExecutionContext
from app.core.errors import (
    ToolExecutionFailed,
    AICoreError,
    ErrorCode,
)
from app.core.events import AIEvent, EventTypes
from app.core.policies import PolicyDecision
from app.services.audit_log import log as audit_log
from app.tools.policy import authorize_tool_call
from app.tools.registry import ToolDefinition

logger = logging.getLogger(__name__)


async def execute_tool(
    ctx: ExecutionContext,
    tool_key: str,
    params: dict[str, Any],
    idempotency_key: Optional[str] = None,
) -> dict[str, Any]:
    """
    Execute a tool through the full authorization → execution → audit pipeline.

    Returns the tool's output dict on success.
    Raises AICoreError subclasses on failure.
    """
    started_at = time.monotonic()

    # ── 1. Authorize ──
    tool, decision = await authorize_tool_call(ctx, tool_key)

    # ── 2. Log intent ──
    _audit_tool_call(ctx, tool, params, "started")

    # ── 3. Handle DRAFT mode (save but don't execute side-effects) ──
    if decision == PolicyDecision.DRAFT:
        result = {
            "status": "draft",
            "tool": tool_key,
            "params": params,
            "message": "Action saved as draft. Requires user confirmation to execute.",
        }
        _audit_tool_call(ctx, tool, params, "drafted", result=result)
        return result

    # ── 4. Execute with timeout ──
    if tool.handler is None:
        raise ToolExecutionFailed(tool_key, f"Tool '{tool_key}' has no handler registered")

    try:
        result = await asyncio.wait_for(
            tool.handler(ctx, params),
            timeout=tool.timeout_seconds,
        )
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - started_at
        _audit_tool_call(ctx, tool, params, "timeout", error=f"Timed out after {elapsed:.1f}s")
        raise ToolExecutionFailed(tool_key, f"Tool '{tool_key}' timed out after {tool.timeout_seconds}s")
    except AICoreError:
        raise  # Let structured errors pass through
    except Exception as e:
        elapsed = time.monotonic() - started_at
        logger.exception("Tool execution failed: %s", tool_key)
        _audit_tool_call(ctx, tool, params, "failed", error=str(e))
        raise ToolExecutionFailed(tool_key, f"Tool '{tool_key}' failed: {type(e).__name__}")

    # ── 5. Audit success ──
    elapsed = time.monotonic() - started_at
    _audit_tool_call(ctx, tool, params, "succeeded", result=result, elapsed_ms=int(elapsed * 1000))

    return result


def _audit_tool_call(
    ctx: ExecutionContext,
    tool: ToolDefinition,
    params: dict,
    status: str,
    result: Optional[dict] = None,
    error: Optional[str] = None,
    elapsed_ms: Optional[int] = None,
) -> None:
    """Fire-and-forget audit entry. Must never raise."""
    try:
        data = {
            "tool_key": tool.key,
            "risk_level": tool.risk_level.value,
            "status": status,
            "agent_mode": ctx.agent_mode.value,
        }
        if elapsed_ms is not None:
            data["elapsed_ms"] = elapsed_ms
        if error:
            data["error"] = error
        # Don't log full params/result — they may contain PII
        data["param_keys"] = list(params.keys()) if params else []

        event_type = {
            "started": EventTypes.TOOL_CALLED,
            "succeeded": EventTypes.TOOL_SUCCEEDED,
            "failed": EventTypes.TOOL_FAILED,
            "timeout": EventTypes.TOOL_FAILED,
            "drafted": EventTypes.TOOL_CALLED,
        }.get(status, EventTypes.TOOL_CALLED)

        audit_log(
            action=event_type,
            detail=data,
            actor=ctx.actor.id,
            channel=f"{ctx.product.value}:{ctx.tenant_id}",
        )
    except Exception:
        pass  # Audit must never crash the main flow
