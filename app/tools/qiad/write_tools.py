"""
QIAD Write Tools — tools that send messages or modify state.

These tools have higher risk levels and go through the policy engine
for approval decisions based on agent mode:
- COPILOT: draft only (saved, not sent)
- ASSISTED: requires human approval before sending
- AUTOPILOT: auto-sends within policy bounds

Tools registered here:
- qiad.conversations.reply   — send a reply (EXTERNAL_COMMUNICATION)
- qiad.conversations.draft   — save a draft reply (LOW_RISK_WRITE)
- qiad.conversations.handoff — request human handoff (LOW_RISK_WRITE)
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.context import ExecutionContext
from app.core.policies import RiskLevel
from app.tools.registry import register_tool

logger = logging.getLogger(__name__)


def _get_qiad_adapter():
    from app.integrations.qiad.adapter import QiadHTTPAdapter
    import os
    base_url = os.getenv("QIAD_API_URL", "http://localhost:3000")
    service_token = os.getenv("QIAD_SERVICE_TOKEN", "")
    return QiadHTTPAdapter(base_url, service_token)


@register_tool(
    key="qiad.conversations.reply",
    version="1.0.0",
    product="qiad",
    description="إرسال رد في محادثة (واتساب/SMS/إيميل) — Send a reply in a conversation",
    risk_level=RiskLevel.EXTERNAL_COMMUNICATION,
    required_permissions=["conversations.reply"],
    input_schema={
        "type": "object",
        "properties": {
            "conversation_id": {"type": "string"},
            "message": {"type": "string", "maxLength": 4096},
            "channel": {"type": "string", "enum": ["whatsapp", "sms", "email", "web"]},
        },
        "required": ["conversation_id", "message", "channel"],
    },
    idempotency_required=True,
    timeout_seconds=30,
)
async def send_reply(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    """
    Send a reply to a customer conversation.

    In COPILOT mode: the executor returns a draft (policy engine handles this).
    In ASSISTED mode: raises ToolApprovalRequired (policy engine handles this).
    In AUTOPILOT mode: sends directly through QIAD's pipeline.
    """
    adapter = _get_qiad_adapter()
    result = await adapter.send_reply(
        ctx,
        conversation_id=params["conversation_id"],
        message=params["message"],
        channel=params["channel"],
    )
    return {
        "sent": True,
        "conversation_id": params["conversation_id"],
        "channel": params["channel"],
        "message_preview": params["message"][:100],
        **result,
    }


@register_tool(
    key="qiad.conversations.draft",
    version="1.0.0",
    product="qiad",
    description="حفظ مسودة رد بدون إرسال — Save a draft reply without sending",
    risk_level=RiskLevel.LOW_RISK_WRITE,
    required_permissions=["conversations.reply"],
    input_schema={
        "type": "object",
        "properties": {
            "conversation_id": {"type": "string"},
            "message": {"type": "string", "maxLength": 4096},
        },
        "required": ["conversation_id", "message"],
    },
    timeout_seconds=10,
)
async def draft_reply(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    """Save a draft reply — always safe, no external side effects."""
    adapter = _get_qiad_adapter()
    result = await adapter.draft_reply(
        ctx,
        conversation_id=params["conversation_id"],
        message=params["message"],
    )
    return {
        "drafted": True,
        "conversation_id": params["conversation_id"],
        "message_preview": params["message"][:100],
        **result,
    }


@register_tool(
    key="qiad.conversations.handoff",
    version="1.0.0",
    product="qiad",
    description="تحويل المحادثة لموظف بشري — Request human agent handoff",
    risk_level=RiskLevel.LOW_RISK_WRITE,
    required_permissions=["conversations.handoff"],
    input_schema={
        "type": "object",
        "properties": {
            "conversation_id": {"type": "string"},
            "reason": {
                "type": "string",
                "description": "Why the AI is requesting handoff",
                "enum": [
                    "customer_request",      # العميل طلب موظف
                    "complex_issue",         # مشكلة معقدة
                    "sensitive_topic",       # موضوع حساس
                    "escalation",            # تصعيد
                    "low_confidence",        # ثقة منخفضة بالإجابة
                    "out_of_scope",          # خارج نطاق الخدمة
                ],
            },
            "summary": {
                "type": "string",
                "description": "AI-generated summary of the conversation for the human agent",
                "maxLength": 1000,
            },
        },
        "required": ["conversation_id", "reason", "summary"],
    },
    timeout_seconds=10,
)
async def request_handoff(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    """
    Request handoff to a human agent.

    This is a LOW_RISK_WRITE because it doesn't send anything to the customer —
    it just flags the conversation for human attention.
    """
    adapter = _get_qiad_adapter()
    result = await adapter.request_handoff(
        ctx,
        conversation_id=params["conversation_id"],
        reason=params["reason"],
        summary=params["summary"],
    )
    return {
        "handoff_requested": True,
        "conversation_id": params["conversation_id"],
        "reason": params["reason"],
        **result,
    }
