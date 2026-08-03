"""
Waslak Insight Store — persists generated merchant order-status insights.
"""
import uuid
import asyncio
from datetime import datetime, timezone
import psycopg2.extras
from app.services.db_pool import pooled_cursor


def _save_insight_sync(
    task_id: str | None,
    merchant_id: str,
    order_summary: dict,
    suggestions: str,
) -> str:
    insight_id = str(uuid.uuid4())
    with pooled_cursor() as cur:
        cur.execute(
            """
            INSERT INTO waslak_insights
              (id, task_id, merchant_id, order_summary, suggestions, created_at)
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (
                insight_id, task_id, merchant_id,
                psycopg2.extras.Json(order_summary),
                suggestions,
                datetime.now(timezone.utc),
            ),
        )
    return insight_id


async def save_insight(
    task_id: str | None,
    merchant_id: str,
    order_summary: dict,
    suggestions: str,
) -> str:
    return await asyncio.to_thread(
        _save_insight_sync, task_id, merchant_id, order_summary, suggestions
    )
