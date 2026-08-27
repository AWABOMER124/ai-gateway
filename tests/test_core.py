"""
Unit tests for core platform modules.

Tests ExecutionContext, policies, errors, security, events,
tool registry, and tool policy — all without database dependencies.
"""
import pytest
import time

from app.core.context import (
    ExecutionContext, Actor, ActorType, Product, AgentMode, legacy_context,
)
from app.core.errors import (
    AICoreError, AuthError, ToolPermissionDenied, ToolApprovalRequired,
    ErrorCode,
)
from app.core.policies import (
    RiskLevel, PolicyDecision, evaluate_policy, check_permission,
    check_tool_access,
)
from app.core.events import AIEvent, EventTypes
from app.core.security import create_service_token, verify_service_token, build_context_from_token
from app.tools.registry import ToolDefinition, ToolRegistry, tool_registry


# ── Fixtures ──────────────────────────────────────────────────────


def _make_ctx(
    tenant_id: str = "tenant_1",
    product: Product = Product.QIAD,
    mode: AgentMode = AgentMode.ASSISTED,
    permissions: tuple = ("*",),
    actor_id: str = "user_1",
) -> ExecutionContext:
    return ExecutionContext(
        tenant_id=tenant_id,
        product=product,
        actor=Actor(type=ActorType.USER, id=actor_id, permissions=permissions),
        agent_mode=mode,
    )


# ── ExecutionContext ──────────────────────────────────────────────


class TestExecutionContext:
    def test_frozen(self):
        ctx = _make_ctx()
        with pytest.raises(AttributeError):
            ctx.tenant_id = "other"

    def test_with_agent(self):
        ctx = _make_ctx()
        new_ctx = ctx.with_agent("agent_123")
        assert new_ctx.agent_id == "agent_123"
        assert ctx.agent_id is None  # Original unchanged

    def test_with_conversation(self):
        ctx = _make_ctx()
        new_ctx = ctx.with_conversation("conv_456", "cust_789")
        assert new_ctx.conversation_id == "conv_456"
        assert new_ctx.customer_id == "cust_789"

    def test_legacy_context(self):
        ctx = legacy_context()
        assert ctx.tenant_id == "legacy"
        assert ctx.product == Product.LEGACY_PERSONAL

    def test_to_log_dict(self):
        ctx = _make_ctx()
        d = ctx.to_log_dict()
        assert d["tenant_id"] == "tenant_1"
        assert d["product"] == "qiad"
        assert "request_id" in d


# ── Errors ────────────────────────────────────────────────────────


class TestErrors:
    def test_error_response_format(self):
        err = AuthError("bad token", request_id="req_1")
        resp = err.to_response()
        assert resp["error"]["code"] == "AUTH_FAILED"
        assert resp["error"]["request_id"] == "req_1"
        assert "bad token" in resp["error"]["message"]

    def test_http_status_mapping(self):
        assert AuthError().http_status == 401
        assert ToolPermissionDenied("test").http_status == 403
        assert ToolApprovalRequired("test").http_status == 403

    def test_no_stack_trace_in_response(self):
        err = AICoreError(ErrorCode.INTERNAL_ERROR, "something broke")
        resp = err.to_response()
        assert "traceback" not in str(resp).lower()
        assert "stack" not in str(resp).lower()


# ── Policies ──────────────────────────────────────────────────────


class TestPolicies:
    def test_off_mode_always_denied(self):
        ctx = _make_ctx(mode=AgentMode.OFF)
        decision = evaluate_policy(RiskLevel.READ_ONLY, ctx)
        assert decision == PolicyDecision.DENIED

    def test_read_only_allowed_in_copilot(self):
        ctx = _make_ctx(mode=AgentMode.COPILOT)
        decision = evaluate_policy(RiskLevel.READ_ONLY, ctx)
        assert decision == PolicyDecision.ALLOW

    def test_external_comm_needs_approval_in_assisted(self):
        ctx = _make_ctx(mode=AgentMode.ASSISTED)
        decision = evaluate_policy(RiskLevel.EXTERNAL_COMMUNICATION, ctx)
        assert decision == PolicyDecision.APPROVAL_REQUIRED

    def test_financial_always_needs_approval(self):
        for mode in [AgentMode.ASSISTED, AgentMode.AUTOPILOT]:
            ctx = _make_ctx(mode=mode)
            decision = evaluate_policy(RiskLevel.FINANCIAL, ctx)
            assert decision == PolicyDecision.APPROVAL_REQUIRED

    def test_destructive_denied_in_copilot(self):
        ctx = _make_ctx(mode=AgentMode.COPILOT)
        decision = evaluate_policy(RiskLevel.DESTRUCTIVE, ctx)
        assert decision == PolicyDecision.DENIED

    def test_tenant_override(self):
        ctx = _make_ctx(mode=AgentMode.ASSISTED)
        policy = {"tool_overrides": {"test.tool": {"assisted": "allow"}}}
        decision = evaluate_policy(
            RiskLevel.FINANCIAL, ctx, tool_key="test.tool", tenant_policy=policy
        )
        assert decision == PolicyDecision.ALLOW

    def test_wildcard_permission(self):
        ctx = _make_ctx(permissions=("*",))
        assert check_permission(ctx, "anything.goes") is True

    def test_specific_permission(self):
        ctx = _make_ctx(permissions=("contacts.view",))
        assert check_permission(ctx, "contacts.view") is True
        assert check_permission(ctx, "contacts.edit") is False


# ── Events ────────────────────────────────────────────────────────


class TestEvents:
    def test_from_context(self):
        ctx = _make_ctx()
        event = AIEvent.from_context(
            ctx, EventTypes.TOOL_CALLED,
            data={"tool_key": "test"},
            resource_type="tool",
        )
        assert event.event_type == "ai.tool.called"
        assert event.tenant_id == "tenant_1"
        assert event.product == "qiad"

    def test_to_dict_excludes_none(self):
        ctx = _make_ctx()
        event = AIEvent.from_context(ctx, EventTypes.AI_RUN_STARTED)
        d = event.to_dict()
        assert "resource_type" not in d  # None values excluded


# ── Security (JWT) ────────────────────────────────────────────────


class TestSecurity:
    def test_roundtrip_token(self, monkeypatch):
        monkeypatch.setenv("AI_CORE_SECRET_QIAD", "test-secret-key-12345")

        token = create_service_token(
            issuer="qiad",
            subject="user_abc",
            organization_id="org_xyz",
            permissions=["contacts.view", "conversations.view"],
        )

        claims = verify_service_token(token)
        assert claims["iss"] == "qiad"
        assert claims["sub"] == "user_abc"
        assert claims["org"] == "org_xyz"
        assert "contacts.view" in claims["permissions"]

    def test_expired_token_rejected(self, monkeypatch):
        monkeypatch.setenv("AI_CORE_SECRET_QIAD", "test-secret-key-12345")

        token = create_service_token(
            issuer="qiad",
            subject="user_abc",
            organization_id="org_xyz",
            permissions=[],
            ttl_seconds=-1,
        )

        with pytest.raises(AuthError, match="expired"):
            verify_service_token(token)

    def test_wrong_secret_rejected(self, monkeypatch):
        monkeypatch.setenv("AI_CORE_SECRET_QIAD", "secret-a")
        token = create_service_token(
            issuer="qiad", subject="u", organization_id="o", permissions=[],
        )

        monkeypatch.setenv("AI_CORE_SECRET_QIAD", "secret-b")
        with pytest.raises(AuthError, match="signature"):
            verify_service_token(token)

    def test_build_context_from_claims(self, monkeypatch):
        monkeypatch.setenv("AI_CORE_SECRET_QIAD", "test-secret")

        token = create_service_token(
            issuer="qiad",
            subject="user_1",
            organization_id="org_1",
            permissions=["contacts.view"],
        )
        claims = verify_service_token(token)
        ctx = build_context_from_token(claims)

        assert ctx.tenant_id == "org_1"
        assert ctx.product == Product.QIAD
        assert ctx.actor.id == "user_1"
        assert "contacts.view" in ctx.actor.permissions


# ── Tool Registry ─────────────────────────────────────────────────


class TestToolRegistry:
    def test_register_and_lookup(self):
        reg = ToolRegistry()
        tool = ToolDefinition(
            key="test.read_contact",
            version="1.0.0",
            product="qiad",
            description="Read a contact",
            risk_level=RiskLevel.READ_ONLY,
            required_permissions=["contacts.view"],
        )
        reg.register(tool)
        assert reg.get("test.read_contact") is not None
        assert reg.is_registered("test.read_contact")
        assert not reg.is_registered("nonexistent")

    def test_product_scope(self):
        reg = ToolRegistry()
        tool = ToolDefinition(
            key="qiad.contacts.view",
            version="1.0.0",
            product="qiad",
            description="QIAD only",
            risk_level=RiskLevel.READ_ONLY,
            required_permissions=[],
        )
        reg.register(tool)
        assert tool.is_available_for(Product.QIAD)
        assert not tool.is_available_for(Product.WASLA)

    def test_wildcard_product(self):
        tool = ToolDefinition(
            key="core.health",
            version="1.0.0",
            product="*",
            description="Available to all",
            risk_level=RiskLevel.READ_ONLY,
            required_permissions=[],
        )
        assert tool.is_available_for(Product.QIAD)
        assert tool.is_available_for(Product.WASLA)

    def test_disable_enable(self):
        reg = ToolRegistry()
        tool = ToolDefinition(
            key="test.disable",
            version="1.0.0",
            product="core",
            description="Disableable",
            risk_level=RiskLevel.READ_ONLY,
            required_permissions=[],
        )
        reg.register(tool)
        reg.disable("test.disable")
        assert not reg.get("test.disable").enabled
        reg.enable("test.disable")
        assert reg.get("test.disable").enabled

    def test_list_filters(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            key="a", version="1.0.0", product="qiad",
            description="", risk_level=RiskLevel.READ_ONLY, required_permissions=[],
        ))
        reg.register(ToolDefinition(
            key="b", version="1.0.0", product="wasla",
            description="", risk_level=RiskLevel.FINANCIAL, required_permissions=[],
        ))

        qiad_tools = reg.list_tools(product=Product.QIAD)
        assert len(qiad_tools) == 1
        assert qiad_tools[0].key == "a"

        financial = reg.list_tools(risk_level=RiskLevel.FINANCIAL)
        assert len(financial) == 1
        assert financial[0].key == "b"
