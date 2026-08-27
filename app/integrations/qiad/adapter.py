"""
QIAD Adapter — secure interface between AI Core and QIAD product.

QIAD (قياد) is the CRM & Customer Operations product.
It runs as a separate service (TanStack Start + Supabase).

This adapter defines the contracts AI Core uses to interact with QIAD.
All calls from AI Core to QIAD go through this adapter — never direct DB access.

Security invariants:
- AI Core never bypasses QIAD's Supabase RLS
- All calls carry the tenant_id from ExecutionContext (verified JWT, not client input)
- Read operations use QIAD's service API with row-level scope
- Write operations go through QIAD's own endpoints (which enforce RLS)
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from app.core.context import ExecutionContext

logger = logging.getLogger(__name__)


# ── Data contracts ──────────────────────────────────────────────────


@dataclass
class QiadContact:
    """Contact record as returned by QIAD."""
    id: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    tags: list[str] = None
    metadata: dict[str, Any] = None

    def __post_init__(self):
        self.tags = self.tags or []
        self.metadata = self.metadata or {}


@dataclass
class QiadConversation:
    """Conversation thread from QIAD."""
    id: str
    contact_id: str
    channel: str  # whatsapp, sms, email, web
    status: str   # open, assigned, resolved, closed
    assigned_to: Optional[str] = None
    last_message_at: Optional[str] = None
    messages: list[dict] = None

    def __post_init__(self):
        self.messages = self.messages or []


@dataclass
class QiadOrder:
    """Order record linked through QIAD's commerce integration."""
    id: str
    contact_id: str
    platform: str        # salla, zid
    platform_order_id: str
    status: str
    total: float
    currency: str = "SAR"
    tracking_number: Optional[str] = None
    shipping_company: Optional[str] = None
    items: list[dict] = None

    def __post_init__(self):
        self.items = self.items or []


@dataclass
class QiadKnowledgeResult:
    """Knowledge base search result from QIAD."""
    chunk_id: str
    content: str
    source: str
    score: float
    metadata: dict[str, Any] = None


# ── Adapter interface ───────────────────────────────────────────────


class QiadAdapterInterface(ABC):
    """
    Interface contract for QIAD integration.

    Implementations:
    - QiadHTTPAdapter: calls QIAD's API over HTTP (production)
    - QiadMockAdapter: in-memory mock for testing

    All methods receive ExecutionContext to enforce tenant isolation.
    """

    # ── Contacts (READ_ONLY) ──

    @abstractmethod
    async def get_contact(self, ctx: ExecutionContext, contact_id: str) -> Optional[QiadContact]:
        """Fetch a single contact by ID within the tenant scope."""
        ...

    @abstractmethod
    async def search_contacts(
        self, ctx: ExecutionContext, query: str, limit: int = 10
    ) -> list[QiadContact]:
        """Search contacts by name, phone, or email."""
        ...

    # ── Conversations (READ_ONLY) ──

    @abstractmethod
    async def get_conversation(
        self, ctx: ExecutionContext, conversation_id: str
    ) -> Optional[QiadConversation]:
        """Fetch a conversation with recent messages."""
        ...

    @abstractmethod
    async def list_conversations(
        self,
        ctx: ExecutionContext,
        contact_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> list[QiadConversation]:
        """List conversations, optionally filtered."""
        ...

    # ── Orders (READ_ONLY via Salla/Zid) ──

    @abstractmethod
    async def get_order(self, ctx: ExecutionContext, order_id: str) -> Optional[QiadOrder]:
        """Fetch order details, including tracking info."""
        ...

    @abstractmethod
    async def search_orders(
        self,
        ctx: ExecutionContext,
        contact_id: Optional[str] = None,
        tracking_number: Optional[str] = None,
        platform_order_id: Optional[str] = None,
        limit: int = 10,
    ) -> list[QiadOrder]:
        """Search orders by various criteria."""
        ...

    # ── Knowledge (READ_ONLY) ──

    @abstractmethod
    async def search_knowledge(
        self, ctx: ExecutionContext, query: str, top_k: int = 5
    ) -> list[QiadKnowledgeResult]:
        """Semantic search over tenant's knowledge base."""
        ...

    # ── Messaging (EXTERNAL_COMMUNICATION — requires approval in ASSISTED mode) ──

    @abstractmethod
    async def send_reply(
        self,
        ctx: ExecutionContext,
        conversation_id: str,
        message: str,
        channel: str,
    ) -> dict:
        """Send a reply in a conversation. Goes through QIAD's send pipeline."""
        ...

    @abstractmethod
    async def draft_reply(
        self,
        ctx: ExecutionContext,
        conversation_id: str,
        message: str,
    ) -> dict:
        """Save a draft reply (COPILOT mode). Does NOT send."""
        ...

    # ── Handoff ──

    @abstractmethod
    async def request_handoff(
        self,
        ctx: ExecutionContext,
        conversation_id: str,
        reason: str,
        summary: str,
    ) -> dict:
        """Request human agent handoff for a conversation."""
        ...


# ── Placeholder HTTP adapter ───────────────────────────────────────


class QiadHTTPAdapter(QiadAdapterInterface):
    """
    Production adapter that calls QIAD's internal API.

    Will be implemented when QIAD exposes its service API.
    For now, all methods raise NotImplementedError with clear messages.
    """

    def __init__(self, base_url: str, service_token: str):
        self.base_url = base_url.rstrip("/")
        self.service_token = service_token

    async def get_contact(self, ctx, contact_id):
        raise NotImplementedError("QIAD HTTP adapter: awaiting QIAD service API")

    async def search_contacts(self, ctx, query, limit=10):
        raise NotImplementedError("QIAD HTTP adapter: awaiting QIAD service API")

    async def get_conversation(self, ctx, conversation_id):
        raise NotImplementedError("QIAD HTTP adapter: awaiting QIAD service API")

    async def list_conversations(self, ctx, contact_id=None, status=None, limit=20):
        raise NotImplementedError("QIAD HTTP adapter: awaiting QIAD service API")

    async def get_order(self, ctx, order_id):
        raise NotImplementedError("QIAD HTTP adapter: awaiting QIAD service API")

    async def search_orders(self, ctx, contact_id=None, tracking_number=None, platform_order_id=None, limit=10):
        raise NotImplementedError("QIAD HTTP adapter: awaiting QIAD service API")

    async def search_knowledge(self, ctx, query, top_k=5):
        raise NotImplementedError("QIAD HTTP adapter: awaiting QIAD service API")

    async def send_reply(self, ctx, conversation_id, message, channel):
        raise NotImplementedError("QIAD HTTP adapter: awaiting QIAD service API")

    async def draft_reply(self, ctx, conversation_id, message):
        raise NotImplementedError("QIAD HTTP adapter: awaiting QIAD service API")

    async def request_handoff(self, ctx, conversation_id, reason, summary):
        raise NotImplementedError("QIAD HTTP adapter: awaiting QIAD service API")
