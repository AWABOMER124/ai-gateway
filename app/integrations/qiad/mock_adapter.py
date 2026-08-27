"""
QIAD Mock Adapter — in-memory implementation for testing.

Used in unit/integration tests and when QIAD service is unavailable.
Enforces the same interface as the production adapter.
"""
from __future__ import annotations

from typing import Any, Optional

from app.core.context import ExecutionContext
from app.integrations.qiad.adapter import (
    QiadAdapterInterface,
    QiadContact,
    QiadConversation,
    QiadOrder,
    QiadKnowledgeResult,
)


class QiadMockAdapter(QiadAdapterInterface):
    """In-memory mock adapter with pre-seeded test data."""

    def __init__(self):
        self._contacts: dict[str, dict[str, QiadContact]] = {}  # tenant_id → {id → contact}
        self._conversations: dict[str, dict[str, QiadConversation]] = {}
        self._orders: dict[str, dict[str, QiadOrder]] = {}
        self._drafts: list[dict] = []
        self._handoffs: list[dict] = []
        self._sent_messages: list[dict] = []

    def seed_contact(self, tenant_id: str, contact: QiadContact) -> None:
        self._contacts.setdefault(tenant_id, {})[contact.id] = contact

    def seed_conversation(self, tenant_id: str, conv: QiadConversation) -> None:
        self._conversations.setdefault(tenant_id, {})[conv.id] = conv

    def seed_order(self, tenant_id: str, order: QiadOrder) -> None:
        self._orders.setdefault(tenant_id, {})[order.id] = order

    # ── Contacts ──

    async def get_contact(self, ctx: ExecutionContext, contact_id: str) -> Optional[QiadContact]:
        return self._contacts.get(ctx.tenant_id, {}).get(contact_id)

    async def search_contacts(self, ctx: ExecutionContext, query: str, limit: int = 10) -> list[QiadContact]:
        contacts = list(self._contacts.get(ctx.tenant_id, {}).values())
        q = query.lower()
        matched = [
            c for c in contacts
            if q in (c.name or "").lower()
            or q in (c.phone or "").lower()
            or q in (c.email or "").lower()
        ]
        return matched[:limit]

    # ── Conversations ──

    async def get_conversation(self, ctx: ExecutionContext, conversation_id: str) -> Optional[QiadConversation]:
        return self._conversations.get(ctx.tenant_id, {}).get(conversation_id)

    async def list_conversations(self, ctx, contact_id=None, status=None, limit=20) -> list[QiadConversation]:
        convs = list(self._conversations.get(ctx.tenant_id, {}).values())
        if contact_id:
            convs = [c for c in convs if c.contact_id == contact_id]
        if status:
            convs = [c for c in convs if c.status == status]
        return convs[:limit]

    # ── Orders ──

    async def get_order(self, ctx: ExecutionContext, order_id: str) -> Optional[QiadOrder]:
        return self._orders.get(ctx.tenant_id, {}).get(order_id)

    async def search_orders(self, ctx, contact_id=None, tracking_number=None, platform_order_id=None, limit=10):
        orders = list(self._orders.get(ctx.tenant_id, {}).values())
        if contact_id:
            orders = [o for o in orders if o.contact_id == contact_id]
        if tracking_number:
            orders = [o for o in orders if o.tracking_number == tracking_number]
        if platform_order_id:
            orders = [o for o in orders if o.platform_order_id == platform_order_id]
        return orders[:limit]

    # ── Knowledge ──

    async def search_knowledge(self, ctx, query, top_k=5) -> list[QiadKnowledgeResult]:
        # Mock: return empty for now
        return []

    # ── Messaging ──

    async def send_reply(self, ctx, conversation_id, message, channel) -> dict:
        entry = {
            "tenant_id": ctx.tenant_id,
            "conversation_id": conversation_id,
            "message": message,
            "channel": channel,
        }
        self._sent_messages.append(entry)
        return {"message_id": f"msg_{len(self._sent_messages)}"}

    async def draft_reply(self, ctx, conversation_id, message) -> dict:
        entry = {
            "tenant_id": ctx.tenant_id,
            "conversation_id": conversation_id,
            "message": message,
        }
        self._drafts.append(entry)
        return {"draft_id": f"draft_{len(self._drafts)}"}

    # ── Handoff ──

    async def request_handoff(self, ctx, conversation_id, reason, summary) -> dict:
        entry = {
            "tenant_id": ctx.tenant_id,
            "conversation_id": conversation_id,
            "reason": reason,
            "summary": summary,
        }
        self._handoffs.append(entry)
        return {"handoff_id": f"handoff_{len(self._handoffs)}"}
