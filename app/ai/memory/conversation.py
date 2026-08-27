"""
3-Layer Conversation Memory for the AI Core platform.

Layer 1 — Recent turns: raw messages from the current conversation (in-context)
Layer 2 — Conversation summary: compressed summary of older messages
Layer 3 — Structured customer memory: persistent facts about the customer

This module manages layers 2 and 3 (layer 1 is the message history itself).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from app.core.context import ExecutionContext
from app.services.db_pool import pooled_cursor

logger = logging.getLogger(__name__)


# ── Layer 2: Conversation Summary ─────────────────────────────────


def _get_conversation_summary_sync(
    tenant_id: str, conversation_id: str
) -> Optional[str]:
    """Fetch the latest conversation summary."""
    with pooled_cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT summary FROM ai_conversation_summaries
            WHERE tenant_id = %s AND conversation_id = %s
            ORDER BY updated_at DESC LIMIT 1
            """,
            (tenant_id, conversation_id),
        )
        row = cur.fetchone()
        return row["summary"] if row else None


def _save_conversation_summary_sync(
    tenant_id: str,
    conversation_id: str,
    summary: str,
    message_count: int,
) -> None:
    """Save or update a conversation summary."""
    import uuid
    from datetime import datetime, timezone

    with pooled_cursor() as cur:
        cur.execute(
            """
            INSERT INTO ai_conversation_summaries
                (id, tenant_id, conversation_id, summary, message_count, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, conversation_id)
            DO UPDATE SET
                summary = EXCLUDED.summary,
                message_count = EXCLUDED.message_count,
                updated_at = EXCLUDED.updated_at
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                conversation_id,
                summary,
                message_count,
                datetime.now(timezone.utc),
            ),
        )


async def get_conversation_summary(
    ctx: ExecutionContext, conversation_id: str
) -> Optional[str]:
    return await asyncio.to_thread(
        _get_conversation_summary_sync, ctx.tenant_id, conversation_id
    )


async def save_conversation_summary(
    ctx: ExecutionContext,
    conversation_id: str,
    summary: str,
    message_count: int,
) -> None:
    await asyncio.to_thread(
        _save_conversation_summary_sync,
        ctx.tenant_id,
        conversation_id,
        summary,
        message_count,
    )


# ── Layer 3: Structured Customer Memory ───────────────────────────


def _get_customer_memory_sync(
    tenant_id: str, customer_id: str
) -> Optional[dict]:
    """Fetch structured memory for a customer."""
    with pooled_cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT memory FROM ai_customer_memory
            WHERE tenant_id = %s AND customer_id = %s
            """,
            (tenant_id, customer_id),
        )
        row = cur.fetchone()
        if row and row.get("memory"):
            return dict(row["memory"]) if isinstance(row["memory"], dict) else json.loads(row["memory"])
        return None


def _save_customer_memory_sync(
    tenant_id: str, customer_id: str, memory: dict
) -> None:
    """Save or update structured customer memory."""
    import uuid
    from datetime import datetime, timezone

    with pooled_cursor() as cur:
        cur.execute(
            """
            INSERT INTO ai_customer_memory
                (id, tenant_id, customer_id, memory, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, customer_id)
            DO UPDATE SET
                memory = EXCLUDED.memory,
                updated_at = EXCLUDED.updated_at
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                customer_id,
                json.dumps(memory, ensure_ascii=False),
                datetime.now(timezone.utc),
            ),
        )


async def get_customer_memory(
    ctx: ExecutionContext, customer_id: str
) -> Optional[dict]:
    return await asyncio.to_thread(
        _get_customer_memory_sync, ctx.tenant_id, customer_id
    )


async def save_customer_memory(
    ctx: ExecutionContext, customer_id: str, memory: dict
) -> None:
    await asyncio.to_thread(
        _save_customer_memory_sync, ctx.tenant_id, customer_id, memory
    )


async def update_customer_memory(
    ctx: ExecutionContext, customer_id: str, updates: dict
) -> dict:
    """
    Merge updates into existing customer memory.
    Returns the merged memory.
    """
    existing = await get_customer_memory(ctx, customer_id) or {}
    existing.update(updates)
    await save_customer_memory(ctx, customer_id, existing)
    return existing


# ── Summary generation helper ─────────────────────────────────────


async def generate_conversation_summary(
    messages: list[dict[str, Any]],
    existing_summary: Optional[str] = None,
) -> str:
    """
    Generate a compressed summary of conversation messages.
    Uses the AI to compress older messages into a summary.
    """
    from app.agents import _openai_chat

    prompt_parts = ["لخص المحادثة التالية في فقرة واحدة مركزة. اذكر المشكلة الأساسية والإجراءات المتخذة والنتيجة."]

    if existing_summary:
        prompt_parts.append(f"\nالملخص السابق: {existing_summary}")

    prompt_parts.append("\nالرسائل:")
    for msg in messages:
        direction = "العميل" if msg.get("direction") != "outbound" else "المساعد"
        prompt_parts.append(f"[{direction}]: {msg.get('content', '')[:200]}")

    summary = await _openai_chat(
        [
            {"role": "system", "content": "أنت مساعد يلخص المحادثات بدقة وإيجاز."},
            {"role": "user", "content": "\n".join(prompt_parts)},
        ],
        max_tokens=300,
    )
    return summary
