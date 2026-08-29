"""
Tests for QIAD tools and mock adapter.

Tests tool registration, product scope, adapter interface,
and tenant isolation using the mock adapter.
"""
import pytest

from app.core.context import ExecutionContext, Actor, ActorType, Product, AgentMode
from app.core.policies import RiskLevel
from app.tools.registry import ToolRegistry, ToolDefinition, tool_registry
from app.integrations.qiad.mock_adapter import QiadMockAdapter
from app.integrations.qiad.adapter import (
    QiadContact, QiadConversation, QiadOrder,
)


# Import to trigger registration
import app.tools.qiad.read_tools  # noqa: F401
import app.tools.qiad.write_tools  # noqa: F401


def _make_ctx(
    tenant_id: str = "tenant_1",
    product: Product = Product.QIAD,
    mode: AgentMode = AgentMode.ASSISTED,
    permissions: tuple = ("*",),
) -> ExecutionContext:
    return ExecutionContext(
        tenant_id=tenant_id,
        product=product,
        actor=Actor(type=ActorType.USER, id="user_1", permissions=permissions),
        agent_mode=mode,
    )


# ── Tool Registration Tests ──────────────────────────────────────


class TestQiadToolRegistration:
    def test_read_tools_registered(self):
        keys = [
            "qiad.contacts.get",
            "qiad.contacts.search",
            "qiad.conversations.get",
            "qiad.conversations.list",
            "qiad.orders.get",
            "qiad.orders.search",
            "qiad.knowledge.search",
        ]
        for key in keys:
            tool = tool_registry.get(key)
            assert tool is not None, f"Tool {key} not registered"
            assert tool.risk_level == RiskLevel.READ_ONLY
            assert tool.product == "qiad"

    def test_write_tools_registered(self):
        reply_tool = tool_registry.get("qiad.conversations.reply")
        assert reply_tool is not None
        assert reply_tool.risk_level == RiskLevel.EXTERNAL_COMMUNICATION

        draft_tool = tool_registry.get("qiad.conversations.draft")
        assert draft_tool is not None
        assert draft_tool.risk_level == RiskLevel.LOW_RISK_WRITE

        handoff_tool = tool_registry.get("qiad.conversations.handoff")
        assert handoff_tool is not None
        assert handoff_tool.risk_level == RiskLevel.LOW_RISK_WRITE

    def test_qiad_tools_scoped_to_qiad(self):
        tool = tool_registry.get("qiad.contacts.get")
        assert tool.is_available_for(Product.QIAD)
        assert not tool.is_available_for(Product.WASLA)

    def test_reply_requires_idempotency(self):
        tool = tool_registry.get("qiad.conversations.reply")
        assert tool.idempotency_required is True


# ── Mock Adapter Tests ────────────────────────────────────────────


class TestQiadMockAdapter:
    def _make_adapter(self):
        adapter = QiadMockAdapter()
        adapter.seed_contact("tenant_1", QiadContact(
            id="c1", name="أحمد محمد", phone="+966501234567", email="ahmed@example.com",
            tags=["vip"],
        ))
        adapter.seed_contact("tenant_1", QiadContact(
            id="c2", name="سارة العلي", phone="+966509876543",
        ))
        adapter.seed_contact("tenant_2", QiadContact(
            id="c3", name="خالد السعيد", phone="+966507777777",
        ))
        adapter.seed_conversation("tenant_1", QiadConversation(
            id="conv1", contact_id="c1", channel="whatsapp", status="open",
            messages=[{"content": "وين طلبي؟", "direction": "inbound"}],
        ))
        adapter.seed_order("tenant_1", QiadOrder(
            id="ord1", contact_id="c1", platform="salla",
            platform_order_id="SAL-12345", status="shipped",
            total=299.0, tracking_number="SMSA-789",
            shipping_company="SMSA Express",
        ))
        return adapter

    def test_get_contact(self):
        import asyncio
        adapter = self._make_adapter()
        ctx = _make_ctx(tenant_id="tenant_1")
        contact = asyncio.run(adapter.get_contact(ctx, "c1"))
        assert contact is not None
        assert contact.name == "أحمد محمد"
        assert contact.phone == "+966501234567"

    def test_tenant_isolation(self):
        import asyncio
        adapter = self._make_adapter()
        ctx1 = _make_ctx(tenant_id="tenant_1")
        ctx2 = _make_ctx(tenant_id="tenant_2")
        assert asyncio.run(adapter.get_contact(ctx1, "c1")) is not None
        assert asyncio.run(adapter.get_contact(ctx1, "c3")) is None
        assert asyncio.run(adapter.get_contact(ctx2, "c3")) is not None
        assert asyncio.run(adapter.get_contact(ctx2, "c1")) is None

    def test_search_contacts(self):
        import asyncio
        adapter = self._make_adapter()
        ctx = _make_ctx(tenant_id="tenant_1")
        results = asyncio.run(adapter.search_contacts(ctx, "أحمد"))
        assert len(results) == 1
        assert results[0].id == "c1"

    def test_search_contacts_by_phone(self):
        import asyncio
        adapter = self._make_adapter()
        ctx = _make_ctx(tenant_id="tenant_1")
        results = asyncio.run(adapter.search_contacts(ctx, "+966501234567"))
        assert len(results) == 1

    def test_get_conversation(self):
        import asyncio
        adapter = self._make_adapter()
        ctx = _make_ctx(tenant_id="tenant_1")
        conv = asyncio.run(adapter.get_conversation(ctx, "conv1"))
        assert conv is not None
        assert conv.channel == "whatsapp"
        assert len(conv.messages) == 1

    def test_get_order(self):
        import asyncio
        adapter = self._make_adapter()
        ctx = _make_ctx(tenant_id="tenant_1")
        order = asyncio.run(adapter.get_order(ctx, "ord1"))
        assert order is not None
        assert order.platform == "salla"
        assert order.tracking_number == "SMSA-789"

    def test_search_orders_by_tracking(self):
        import asyncio
        adapter = self._make_adapter()
        ctx = _make_ctx(tenant_id="tenant_1")
        orders = asyncio.run(adapter.search_orders(ctx, tracking_number="SMSA-789"))
        assert len(orders) == 1
        assert orders[0].id == "ord1"

    def test_send_reply(self):
        import asyncio
        adapter = self._make_adapter()
        ctx = _make_ctx(tenant_id="tenant_1")
        result = asyncio.run(adapter.send_reply(ctx, "conv1", "طلبك في الطريق!", "whatsapp"))
        assert "message_id" in result
        assert len(adapter._sent_messages) == 1
        assert adapter._sent_messages[0]["tenant_id"] == "tenant_1"

    def test_draft_reply(self):
        import asyncio
        adapter = self._make_adapter()
        ctx = _make_ctx(tenant_id="tenant_1")
        result = asyncio.run(adapter.draft_reply(ctx, "conv1", "مسودة الرد"))
        assert "draft_id" in result
        assert len(adapter._drafts) == 1

    def test_handoff(self):
        import asyncio
        adapter = self._make_adapter()
        ctx = _make_ctx(tenant_id="tenant_1")
        result = asyncio.run(adapter.request_handoff(
            ctx, "conv1", "customer_request", "العميل طلب موظف"
        ))
        assert "handoff_id" in result
        assert len(adapter._handoffs) == 1

    def test_cross_tenant_message_isolation(self):
        import asyncio
        adapter = self._make_adapter()
        ctx1 = _make_ctx(tenant_id="tenant_1")
        asyncio.run(adapter.send_reply(ctx1, "conv1", "رسالة تينانت 1", "whatsapp"))
        assert adapter._sent_messages[0]["tenant_id"] == "tenant_1"
