"""
QIAD Read-Only Tools — safe tools for reading CRM data.

All tools here are READ_ONLY risk level (always allowed except in OFF mode).
They go through the QIAD adapter, which enforces tenant isolation via
Supabase RLS — AI Core never queries QIAD's database directly.

Tools registered here:
- qiad.contacts.get       — fetch a single contact
- qiad.contacts.search    — search contacts by name/phone/email
- qiad.conversations.get  — fetch a conversation with messages
- qiad.conversations.list — list conversations (filtered)
- qiad.orders.get         — fetch order details + tracking
- qiad.orders.search      — search orders by contact/tracking/platform ID
- qiad.knowledge.search   — semantic search over tenant knowledge base
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.context import ExecutionContext
from app.core.policies import RiskLevel
from app.tools.registry import register_tool

logger = logging.getLogger(__name__)


def _get_qiad_adapter():
    """Lazy import to avoid circular dependencies and allow mock injection."""
    from app.integrations.qiad.adapter import QiadHTTPAdapter
    import os
    base_url = os.getenv("QIAD_API_URL", "http://localhost:3000")
    service_token = os.getenv("QIAD_SERVICE_TOKEN", "")
    return QiadHTTPAdapter(base_url, service_token)


# ── Contacts ──────────────────────────────────────────────────────


@register_tool(
    key="qiad.contacts.get",
    version="1.0.0",
    product="qiad",
    description="جلب بيانات جهة اتصال واحدة بالمعرف — Fetch a single contact by ID",
    risk_level=RiskLevel.READ_ONLY,
    required_permissions=["contacts.view"],
    input_schema={
        "type": "object",
        "properties": {
            "contact_id": {"type": "string", "description": "Contact ID in QIAD"},
        },
        "required": ["contact_id"],
    },
    timeout_seconds=10,
)
async def get_contact(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_qiad_adapter()
    contact = await adapter.get_contact(ctx, params["contact_id"])
    if contact is None:
        return {"found": False, "contact": None}
    return {
        "found": True,
        "contact": {
            "id": contact.id,
            "name": contact.name,
            "phone": contact.phone,
            "email": contact.email,
            "tags": contact.tags,
        },
    }


@register_tool(
    key="qiad.contacts.search",
    version="1.0.0",
    product="qiad",
    description="بحث في جهات الاتصال بالاسم أو الجوال أو الإيميل — Search contacts",
    risk_level=RiskLevel.READ_ONLY,
    required_permissions=["contacts.view"],
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search term (name, phone, or email)"},
            "limit": {"type": "integer", "default": 10, "maximum": 50},
        },
        "required": ["query"],
    },
    timeout_seconds=10,
)
async def search_contacts(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_qiad_adapter()
    contacts = await adapter.search_contacts(
        ctx, params["query"], limit=params.get("limit", 10)
    )
    return {
        "count": len(contacts),
        "contacts": [
            {"id": c.id, "name": c.name, "phone": c.phone, "email": c.email, "tags": c.tags}
            for c in contacts
        ],
    }


# ── Conversations ─────────────────────────────────────────────────


@register_tool(
    key="qiad.conversations.get",
    version="1.0.0",
    product="qiad",
    description="جلب محادثة مع آخر الرسائل — Fetch a conversation with recent messages",
    risk_level=RiskLevel.READ_ONLY,
    required_permissions=["conversations.view"],
    input_schema={
        "type": "object",
        "properties": {
            "conversation_id": {"type": "string"},
        },
        "required": ["conversation_id"],
    },
    timeout_seconds=15,
)
async def get_conversation(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_qiad_adapter()
    conv = await adapter.get_conversation(ctx, params["conversation_id"])
    if conv is None:
        return {"found": False, "conversation": None}
    return {
        "found": True,
        "conversation": {
            "id": conv.id,
            "contact_id": conv.contact_id,
            "channel": conv.channel,
            "status": conv.status,
            "assigned_to": conv.assigned_to,
            "last_message_at": conv.last_message_at,
            "messages": conv.messages[-20:],  # Last 20 messages only
        },
    }


@register_tool(
    key="qiad.conversations.list",
    version="1.0.0",
    product="qiad",
    description="قائمة المحادثات مع فلترة — List conversations with optional filters",
    risk_level=RiskLevel.READ_ONLY,
    required_permissions=["conversations.view"],
    input_schema={
        "type": "object",
        "properties": {
            "contact_id": {"type": "string", "description": "Filter by contact"},
            "status": {"type": "string", "enum": ["open", "assigned", "resolved", "closed"]},
            "limit": {"type": "integer", "default": 20, "maximum": 50},
        },
    },
    timeout_seconds=10,
)
async def list_conversations(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_qiad_adapter()
    convs = await adapter.list_conversations(
        ctx,
        contact_id=params.get("contact_id"),
        status=params.get("status"),
        limit=params.get("limit", 20),
    )
    return {
        "count": len(convs),
        "conversations": [
            {
                "id": c.id,
                "contact_id": c.contact_id,
                "channel": c.channel,
                "status": c.status,
                "assigned_to": c.assigned_to,
                "last_message_at": c.last_message_at,
            }
            for c in convs
        ],
    }


# ── Orders ────────────────────────────────────────────────────────


@register_tool(
    key="qiad.orders.get",
    version="1.0.0",
    product="qiad",
    description="جلب تفاصيل طلب مع معلومات التتبع — Fetch order details with tracking",
    risk_level=RiskLevel.READ_ONLY,
    required_permissions=["orders.view"],
    input_schema={
        "type": "object",
        "properties": {
            "order_id": {"type": "string"},
        },
        "required": ["order_id"],
    },
    timeout_seconds=15,
)
async def get_order(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_qiad_adapter()
    order = await adapter.get_order(ctx, params["order_id"])
    if order is None:
        return {"found": False, "order": None}
    return {
        "found": True,
        "order": {
            "id": order.id,
            "contact_id": order.contact_id,
            "platform": order.platform,
            "platform_order_id": order.platform_order_id,
            "status": order.status,
            "total": order.total,
            "currency": order.currency,
            "tracking_number": order.tracking_number,
            "shipping_company": order.shipping_company,
            "items": order.items,
        },
    }


@register_tool(
    key="qiad.orders.search",
    version="1.0.0",
    product="qiad",
    description="بحث في الطلبات برقم التتبع أو رقم الطلب — Search orders",
    risk_level=RiskLevel.READ_ONLY,
    required_permissions=["orders.view"],
    input_schema={
        "type": "object",
        "properties": {
            "contact_id": {"type": "string"},
            "tracking_number": {"type": "string"},
            "platform_order_id": {"type": "string"},
            "limit": {"type": "integer", "default": 10, "maximum": 50},
        },
    },
    timeout_seconds=15,
)
async def search_orders(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_qiad_adapter()
    orders = await adapter.search_orders(
        ctx,
        contact_id=params.get("contact_id"),
        tracking_number=params.get("tracking_number"),
        platform_order_id=params.get("platform_order_id"),
        limit=params.get("limit", 10),
    )
    return {
        "count": len(orders),
        "orders": [
            {
                "id": o.id,
                "contact_id": o.contact_id,
                "platform": o.platform,
                "platform_order_id": o.platform_order_id,
                "status": o.status,
                "total": o.total,
                "currency": o.currency,
                "tracking_number": o.tracking_number,
                "shipping_company": o.shipping_company,
            }
            for o in orders
        ],
    }


# ── Knowledge ─────────────────────────────────────────────────────


@register_tool(
    key="qiad.knowledge.search",
    version="1.0.0",
    product="qiad",
    description="بحث دلالي في قاعدة المعرفة — Semantic search over knowledge base",
    risk_level=RiskLevel.READ_ONLY,
    required_permissions=["knowledge.view"],
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query in natural language"},
            "top_k": {"type": "integer", "default": 5, "maximum": 20},
        },
        "required": ["query"],
    },
    timeout_seconds=15,
)
async def search_knowledge(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_qiad_adapter()
    results = await adapter.search_knowledge(
        ctx, params["query"], top_k=params.get("top_k", 5)
    )
    return {
        "count": len(results),
        "results": [
            {
                "chunk_id": r.chunk_id,
                "content": r.content,
                "source": r.source,
                "score": r.score,
            }
            for r in results
        ],
    }
