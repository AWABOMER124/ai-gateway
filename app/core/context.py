"""
ExecutionContext — the identity envelope for every AI Core request.

Every operation in the multi-tenant AI Core must carry an ExecutionContext
that identifies: who is asking (tenant, actor), what product, which agent,
and a unique request_id for tracing. Tenant identity is NEVER trusted from
client input — it comes from verified auth (JWT claims or API key lookup).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ActorType(str, Enum):
    USER = "user"
    AGENT = "agent"
    SERVICE = "service"
    SYSTEM = "system"


class Product(str, Enum):
    QIAD = "qiad"
    WASLA = "wasla"
    LEGACY_PERSONAL = "legacy_personal"
    EASY_DELIVERY = "easy_delivery"


class AgentMode(str, Enum):
    OFF = "off"
    COPILOT = "copilot"
    ASSISTED = "assisted"
    AUTOPILOT = "autopilot"


@dataclass(frozen=True)
class Actor:
    """Who is performing the action."""
    type: ActorType
    id: str
    display_name: Optional[str] = None
    permissions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionContext:
    """
    Immutable request envelope carrying verified identity and scope.

    NEVER constructed from raw client input. Built by auth middleware
    from verified JWT claims or API key lookup.
    """
    tenant_id: str
    product: Product
    actor: Actor
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: Optional[str] = None
    agent_id: Optional[str] = None
    agent_mode: AgentMode = AgentMode.COPILOT
    conversation_id: Optional[str] = None
    customer_id: Optional[str] = None
    channel: Optional[str] = None
    language: str = "ar"

    def with_agent(self, agent_id: str, agent_mode: AgentMode = AgentMode.COPILOT) -> ExecutionContext:
        """Return a new context scoped to a specific agent."""
        return ExecutionContext(
            tenant_id=self.tenant_id,
            product=self.product,
            actor=self.actor,
            request_id=self.request_id,
            workspace_id=self.workspace_id,
            agent_id=agent_id,
            agent_mode=agent_mode,
            conversation_id=self.conversation_id,
            customer_id=self.customer_id,
            channel=self.channel,
            language=self.language,
        )

    def with_conversation(self, conversation_id: str, customer_id: Optional[str] = None) -> ExecutionContext:
        """Return a new context scoped to a conversation."""
        return ExecutionContext(
            tenant_id=self.tenant_id,
            product=self.product,
            actor=self.actor,
            request_id=self.request_id,
            workspace_id=self.workspace_id,
            agent_id=self.agent_id,
            agent_mode=self.agent_mode,
            conversation_id=conversation_id,
            customer_id=customer_id or self.customer_id,
            channel=self.channel,
            language=self.language,
        )

    def to_log_dict(self) -> dict:
        """Safe representation for structured logging (no secrets)."""
        return {
            "request_id": self.request_id,
            "tenant_id": self.tenant_id,
            "product": self.product.value,
            "actor_type": self.actor.type.value,
            "actor_id": self.actor.id,
            "agent_id": self.agent_id,
            "agent_mode": self.agent_mode.value,
            "conversation_id": self.conversation_id,
            "customer_id": self.customer_id,
            "channel": self.channel,
        }


# Legacy compatibility: build an ExecutionContext for the existing single-user system
def legacy_context(user_id: str = "awab", channel: str = "telegram") -> ExecutionContext:
    """
    Build a context for legacy (pre-multi-tenant) API calls.
    Used by existing /agent/*, /waslak/*, /email/* endpoints
    to maintain backward compatibility.
    """
    return ExecutionContext(
        tenant_id="legacy",
        product=Product.LEGACY_PERSONAL,
        actor=Actor(type=ActorType.USER, id=user_id, permissions=("*",)),
        channel=channel,
    )
