"""
OpenAI Usage — records every chat/embedding call and enforces a soft daily
spend cap (OPENAI_DAILY_SPEND_LIMIT_USD). Added after an audit found zero
spend guardrails anywhere: every agent (supervisor, reviewer, waslak_agent,
olivery_agent, email_agent, writing_agent, file_agent) plus the RAG /ask and
/search pipeline called OpenAI directly with no cap and no usage log.

Pricing below is an approximate list-price estimate per 1K tokens, not exact
billing — good enough for a circuit breaker against a runaway bill, not for
finance-grade accounting. Update PRICING_PER_1K if OpenAI's list prices change
or a different CHAT_MODEL/EMBEDDING_MODEL is configured.
"""
import os
import asyncio
from app.services.db_pool import pooled_cursor

# USD per 1,000 tokens: (input, output). Embedding models have no separate
# output cost, so output is 0.
PRICING_PER_1K = {
    "gpt-4.1-mini": (0.0004, 0.0016),
    "gpt-4.1": (0.002, 0.008),
    "gpt-4o": (0.0025, 0.01),
    "gpt-4o-mini": (0.00015, 0.0006),
    "text-embedding-3-small": (0.00002, 0.0),
    "text-embedding-3-large": (0.00013, 0.0),
}
_DEFAULT_PRICE = (0.001, 0.003)  # conservative fallback for an unlisted model


def _estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_price, out_price = PRICING_PER_1K.get(model, _DEFAULT_PRICE)
    return (prompt_tokens / 1000) * in_price + (completion_tokens / 1000) * out_price


class SpendLimitExceeded(Exception):
    pass


def _daily_limit_usd() -> float:
    raw = os.getenv("OPENAI_DAILY_SPEND_LIMIT_USD", "10.0")
    try:
        return float(raw)
    except ValueError:
        return 10.0


def _get_spend_today_sync() -> float:
    with pooled_cursor(commit=False) as cur:
        cur.execute(
            "SELECT COALESCE(SUM(estimated_cost_usd), 0) AS total "
            "FROM openai_usage_log WHERE created_at >= date_trunc('day', now())"
        )
        row = cur.fetchone()
        return float(row["total"]) if row else 0.0


def _record_usage_sync(
    endpoint: str,
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    estimated_cost_usd: float,
) -> None:
    with pooled_cursor() as cur:
        cur.execute(
            """
            INSERT INTO openai_usage_log
              (endpoint, model, prompt_tokens, completion_tokens, total_tokens, estimated_cost_usd)
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (endpoint, model, prompt_tokens, completion_tokens, total_tokens, estimated_cost_usd),
        )


async def check_spend_cap() -> None:
    """Raises SpendLimitExceeded if today's recorded spend is already at/over
    the configured daily limit. Call BEFORE making an OpenAI request."""
    limit = _daily_limit_usd()
    if limit <= 0:
        return  # 0 or negative = cap disabled, logging still happens
    spent = await asyncio.to_thread(_get_spend_today_sync)
    if spent >= limit:
        raise SpendLimitExceeded(
            f"Daily OpenAI spend cap reached (${spent:.2f} >= ${limit:.2f}). "
            f"Raise OPENAI_DAILY_SPEND_LIMIT_USD in .env to allow more."
        )


async def record_usage(
    endpoint: str,
    model: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
) -> None:
    """Call AFTER a successful OpenAI response, with whatever token counts
    the API returned (chat gives prompt+completion, embeddings give only
    total/prompt)."""
    cost = _estimate_cost_usd(model, prompt_tokens or 0, completion_tokens or 0)
    await asyncio.to_thread(
        _record_usage_sync, endpoint, model, prompt_tokens, completion_tokens, total_tokens, cost
    )


async def get_spend_today() -> float:
    return await asyncio.to_thread(_get_spend_today_sync)


# Sync variants — for the RAG pipeline (app/rag/*), whose call sites are
# plain sync functions (run in FastAPI's thread pool, no event loop to
# await into). Same underlying logic as the async versions above.
def check_spend_cap_sync() -> None:
    limit = _daily_limit_usd()
    if limit <= 0:
        return
    spent = _get_spend_today_sync()
    if spent >= limit:
        raise SpendLimitExceeded(
            f"Daily OpenAI spend cap reached (${spent:.2f} >= ${limit:.2f}). "
            f"Raise OPENAI_DAILY_SPEND_LIMIT_USD in .env to allow more."
        )


def record_usage_sync(
    endpoint: str,
    model: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
) -> None:
    cost = _estimate_cost_usd(model, prompt_tokens or 0, completion_tokens or 0)
    _record_usage_sync(endpoint, model, prompt_tokens, completion_tokens, total_tokens, cost)
