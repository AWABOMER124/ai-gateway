"""
Event contracts — standardized event format for the AI Core platform.

Events are not yet published to an event bus (Phase 2). This module
defines the contract so that all audit log entries and future event
consumers share the same structure.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.context import ExecutionContext


@dataclass
class AIEvent:
    """Standardized event envelope."""
    event_type: str
    product: str
    tenant_id: str
    actor_type: str
    actor_id: str
    data: dict[str, Any] = field(default_factory=dict)
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    request_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_context(
        cls,
        ctx: ExecutionContext,
        event_type: str,
        data: Optional[dict] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
    ) -> AIEvent:
        return cls(
            event_type=event_type,
            product=ctx.product.value,
            tenant_id=ctx.tenant_id,
            actor_type=ctx.actor.type.value,
            actor_id=ctx.actor.id,
            data=data or {},
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=ctx.request_id,
        )


# Event type constants (not exhaustive — new types added as needed)
class EventTypes:
    # AI runs
    AI_RUN_STARTED = "ai.run.started"
    AI_RUN_COMPLETED = "ai.run.completed"
    AI_RUN_FAILED = "ai.run.failed"

    # Tool calls
    TOOL_CALLED = "ai.tool.called"
    TOOL_SUCCEEDED = "ai.tool.succeeded"
    TOOL_FAILED = "ai.tool.failed"
    TOOL_APPROVAL_REQUESTED = "ai.tool.approval_requested"

    # Agent actions
    AGENT_HANDOFF = "ai.agent.handoff"
    AGENT_REPLY_DRAFT = "ai.agent.reply_draft"
    AGENT_REPLY_SENT = "ai.agent.reply_sent"

    # Security
    AUTH_FAILED = "security.auth_failed"
    CROSS_TENANT_ATTEMPT = "security.cross_tenant_attempt"
    PERMISSION_DENIED = "security.permission_denied"
