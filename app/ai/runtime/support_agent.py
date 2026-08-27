"""
QIAD Support Agent — AI-powered customer service agent.

Handles customer conversations across channels (WhatsApp, SMS, email, web).
Uses the tool registry for all actions — never directly accesses QIAD data.

Agent loop:
1. Receive conversation context (messages, contact info, order data)
2. Search knowledge base for relevant answers
3. Generate a response considering conversation history
4. Either draft or send based on agent mode (via tool executor)
5. If confidence is low or issue is complex → request handoff

The agent NEVER:
- Fabricates order statuses or tracking numbers
- Promises things outside policy (refunds, replacements)
- Sends messages without going through the tool executor
- Accesses data outside the tenant scope
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.context import ExecutionContext, AgentMode
from app.core.events import AIEvent, EventTypes
from app.services.audit_log import log as audit_log

logger = logging.getLogger(__name__)

# System prompt for the support agent (bilingual Arabic/English)
SUPPORT_SYSTEM_PROMPT = """أنت مساعد خدمة عملاء ذكي يعمل لصالح التاجر. مهمتك مساعدة العملاء بطريقة احترافية وودودة.

## القواعد الأساسية:
1. **لا تخترع بيانات**: إذا ما عندك معلومة عن طلب أو تتبع، قل للعميل بصراحة
2. **لا تعد بشيء خارج الصلاحيات**: لا تعد باسترجاع أو تعويض بدون موافقة
3. **اللغة**: رد بنفس لغة العميل. إذا كتب بالعربي رد بالعربي، إذا كتب بالإنجليزي رد بالإنجليزي
4. **التصعيد**: إذا المشكلة معقدة أو العميل غاضب أو طلب موظف → حول المحادثة فوراً
5. **الخصوصية**: لا تكشف بيانات عملاء آخرين أو معلومات داخلية

## المعلومات المتاحة لك:
- بيانات العميل (الاسم، الجوال، الإيميل)
- تاريخ المحادثة
- بيانات الطلبات (الحالة، التتبع، المنتجات)
- قاعدة المعرفة (سياسات، أسئلة شائعة)

## متى تحول للموظف:
- العميل طلب موظف صراحة
- مشكلة مالية (استرجاع، تعويض)
- شكوى حادة أو عميل غاضب جداً
- موضوع خارج نطاق معرفتك
- ثقتك بالإجابة أقل من 70%

You are a smart customer service assistant working for the merchant. Help customers professionally and warmly.
When uncertain, always err on the side of requesting a human handoff rather than providing incorrect information.
"""


async def run_support_agent(
    ctx: ExecutionContext,
    conversation_id: str,
    messages: list[dict[str, Any]],
    contact: Optional[dict] = None,
    orders: Optional[list[dict]] = None,
    knowledge_results: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """
    Run the support agent for a customer conversation.

    This is the main entry point for AI-powered customer service.
    It orchestrates the full loop: context gathering, generation, and action.

    Args:
        ctx: ExecutionContext with verified tenant/actor identity
        conversation_id: The QIAD conversation ID
        messages: Recent conversation messages
        contact: Contact info (if available)
        orders: Relevant orders (if available)
        knowledge_results: Pre-fetched knowledge base results (if available)

    Returns:
        dict with the agent's action (draft/send/handoff) and metadata
    """
    from app.agents import _openai_chat
    from app.tools.executor import execute_tool

    # Log the AI run start
    audit_log(
        action=EventTypes.AI_RUN_STARTED,
        detail={
            "agent": "support",
            "conversation_id": conversation_id,
            "message_count": len(messages),
            "agent_mode": ctx.agent_mode.value,
        },
        actor=ctx.actor.id,
        channel=f"{ctx.product.value}:{ctx.tenant_id}",
    )

    # ── Build the prompt context ──
    prompt_parts = [SUPPORT_SYSTEM_PROMPT]

    if contact:
        prompt_parts.append(f"\n## بيانات العميل:\nالاسم: {contact.get('name', 'غير معروف')}")
        if contact.get("phone"):
            prompt_parts.append(f"الجوال: {contact['phone']}")
        if contact.get("tags"):
            prompt_parts.append(f"التصنيف: {', '.join(contact['tags'])}")

    if orders:
        prompt_parts.append("\n## الطلبات الأخيرة:")
        for order in orders[:5]:  # Max 5 orders in context
            prompt_parts.append(
                f"- طلب #{order.get('platform_order_id', order.get('id', '?'))}: "
                f"الحالة: {order.get('status', '?')}, "
                f"المبلغ: {order.get('total', '?')} {order.get('currency', 'SAR')}"
            )
            if order.get("tracking_number"):
                prompt_parts.append(f"  رقم التتبع: {order['tracking_number']}")
            if order.get("shipping_company"):
                prompt_parts.append(f"  شركة الشحن: {order['shipping_company']}")

    if knowledge_results:
        prompt_parts.append("\n## معلومات من قاعدة المعرفة:")
        for kr in knowledge_results[:3]:  # Max 3 knowledge chunks
            prompt_parts.append(f"- [{kr.get('source', 'unknown')}]: {kr.get('content', '')[:500]}")

    system_message = "\n".join(prompt_parts)

    # ── Format conversation history as chat messages ──
    chat_messages = [{"role": "system", "content": system_message}]

    for msg in messages[-20:]:  # Last 20 messages
        role = "assistant" if msg.get("direction") == "outbound" else "user"
        chat_messages.append({"role": role, "content": msg.get("content", "")})

    # ── Generate the AI response ──
    try:
        response_text = await _openai_chat(
            chat_messages,
            model=None,  # Uses default from config
            max_tokens=800,
            json_mode=True,
        )

        import json
        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError:
            # If not JSON, treat as plain text response
            response_data = {
                "action": "reply",
                "message": response_text,
                "confidence": 0.7,
            }

    except Exception as e:
        logger.error("Support agent generation failed: %s", e)
        audit_log(
            action=EventTypes.AI_RUN_FAILED,
            detail={"agent": "support", "error": str(e)},
            actor=ctx.actor.id,
            channel=f"{ctx.product.value}:{ctx.tenant_id}",
        )
        return {
            "action": "handoff",
            "reason": "ai_error",
            "summary": "فشل في توليد الرد — يحتاج تدخل موظف",
            "error": str(e),
        }

    # ── Decide on action based on response and agent mode ──
    action = response_data.get("action", "reply")
    confidence = response_data.get("confidence", 0.5)
    message = response_data.get("message", "")

    # Low confidence or explicit handoff request → handoff
    if action == "handoff" or confidence < 0.5:
        try:
            result = await execute_tool(
                ctx=ctx.with_agent("support_agent", ctx.agent_mode),
                tool_key="qiad.conversations.handoff",
                params={
                    "conversation_id": conversation_id,
                    "reason": response_data.get("handoff_reason", "low_confidence"),
                    "summary": response_data.get("summary", message[:500]),
                },
            )
            return {"action": "handoff", **result}
        except Exception as e:
            logger.warning("Handoff tool failed: %s", e)
            return {"action": "handoff", "error": str(e)}

    # Normal reply → route through tool executor (respects agent mode)
    agent_ctx = ctx.with_agent("support_agent", ctx.agent_mode)

    if ctx.agent_mode == AgentMode.COPILOT:
        # In copilot mode, always draft
        tool_key = "qiad.conversations.draft"
        params = {"conversation_id": conversation_id, "message": message}
    else:
        # In assisted/autopilot, try to send (policy engine decides)
        tool_key = "qiad.conversations.reply"
        channel = _detect_channel(messages)
        params = {
            "conversation_id": conversation_id,
            "message": message,
            "channel": channel,
        }

    try:
        result = await execute_tool(
            ctx=agent_ctx,
            tool_key=tool_key,
            params=params,
        )
    except Exception as e:
        # If send fails due to approval requirement, fall back to draft
        logger.info("Tool %s needs approval, falling back to draft: %s", tool_key, e)
        try:
            result = await execute_tool(
                ctx=agent_ctx,
                tool_key="qiad.conversations.draft",
                params={"conversation_id": conversation_id, "message": message},
            )
        except Exception as draft_err:
            return {"action": "error", "error": str(draft_err)}

    # ── Log completion ──
    audit_log(
        action=EventTypes.AI_RUN_COMPLETED,
        detail={
            "agent": "support",
            "conversation_id": conversation_id,
            "action": action,
            "confidence": confidence,
            "agent_mode": ctx.agent_mode.value,
        },
        actor=ctx.actor.id,
        channel=f"{ctx.product.value}:{ctx.tenant_id}",
    )

    return {
        "action": result.get("status", action),
        "confidence": confidence,
        "message_preview": message[:100],
        **result,
    }


def _detect_channel(messages: list[dict]) -> str:
    """Detect the conversation channel from message history."""
    for msg in reversed(messages):
        channel = msg.get("channel")
        if channel:
            return channel
    return "web"  # Default fallback
