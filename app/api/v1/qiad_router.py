"""
QIAD-specific API v1 endpoints.

These endpoints are called by QIAD to trigger AI operations
on customer conversations. All require service JWT auth.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.v1.router import _extract_context
from app.core.errors import AICoreError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/qiad", tags=["v1-qiad"])


# ── Request/Response models ────────────────────────────────────────


class SupportAgentRequest(BaseModel):
    conversation_id: str
    messages: list[dict[str, Any]] = Field(
        ..., description="Recent conversation messages"
    )
    contact: Optional[dict[str, Any]] = Field(
        None, description="Contact info from QIAD"
    )
    orders: Optional[list[dict[str, Any]]] = Field(
        None, description="Relevant orders"
    )
    knowledge_query: Optional[str] = Field(
        None, description="Auto-search knowledge base with this query"
    )


class SupportAgentResponse(BaseModel):
    action: str  # reply, draft, handoff, error
    confidence: Optional[float] = None
    message_preview: Optional[str] = None
    handoff_requested: Optional[bool] = None
    reason: Optional[str] = None
    error: Optional[str] = None
    request_id: Optional[str] = None


# ── Endpoints ──────────────────────────────────────────────────────


@router.post("/support", response_model=SupportAgentResponse)
async def run_support(
    body: SupportAgentRequest,
    authorization: str = Header(...),
):
    """
    Trigger the AI support agent for a customer conversation.

    Called by QIAD when a new message arrives or when the agent
    needs to handle a conversation. The response indicates what
    the AI did (drafted a reply, sent a reply, requested handoff).
    """
    ctx = await _extract_context(authorization)

    try:
        from app.ai.runtime.support_agent import run_support_agent

        # Optionally search knowledge base
        knowledge_results = None
        if body.knowledge_query:
            try:
                from app.tools.executor import execute_tool
                kr = await execute_tool(
                    ctx=ctx,
                    tool_key="qiad.knowledge.search",
                    params={"query": body.knowledge_query, "top_k": 3},
                )
                knowledge_results = kr.get("results", [])
            except Exception as e:
                logger.warning("Knowledge search failed: %s", e)

        result = await run_support_agent(
            ctx=ctx,
            conversation_id=body.conversation_id,
            messages=body.messages,
            contact=body.contact,
            orders=body.orders,
            knowledge_results=knowledge_results,
        )

        return SupportAgentResponse(
            action=result.get("action", "error"),
            confidence=result.get("confidence"),
            message_preview=result.get("message_preview"),
            handoff_requested=result.get("handoff_requested"),
            reason=result.get("reason"),
            error=result.get("error"),
            request_id=ctx.request_id,
        )

    except AICoreError as e:
        return JSONResponse(
            status_code=e.http_status,
            content=e.to_response(),
        )
    except Exception as e:
        logger.exception("Support agent error")
        return SupportAgentResponse(
            action="error",
            error=f"Internal error: {type(e).__name__}",
            request_id=ctx.request_id,
        )


@router.get("/conversations/{conversation_id}/ai-history")
async def get_ai_history(
    conversation_id: str,
    authorization: str = Header(...),
    limit: int = 20,
):
    """
    Get AI run history for a conversation.

    Shows what the AI did, when, and with what confidence.
    Useful for the QIAD dashboard to display AI activity.
    """
    ctx = await _extract_context(authorization)

    import asyncio
    from app.services.db_pool import pooled_cursor

    def _fetch():
        with pooled_cursor(commit=False) as cur:
            cur.execute(
                """
                SELECT id, agent_type, status, action_taken, confidence,
                       output_summary, tools_called, elapsed_ms, created_at
                FROM ai_runs
                WHERE tenant_id = %s AND conversation_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (ctx.tenant_id, conversation_id, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    try:
        runs = await asyncio.to_thread(_fetch)
    except Exception:
        runs = []  # Table may not exist yet

    return {
        "conversation_id": conversation_id,
        "runs": runs,
    }
