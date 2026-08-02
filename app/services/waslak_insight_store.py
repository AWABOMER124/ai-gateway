"""
Waslak Insight Store — persists generated merchant order-status insights.
"""
import os
import uuid
import asyncio
from datetime import datetime, timezone
import psycopg2
import psycopg2.extras


def _get_conn():
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        return psycopg2.connect(db_url)
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "awab_ai"),
        user=os.getenv("POSTGRES_USER", "awab_ai"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


def _save_insight_sync(
    task_id: str | None,
    merchant_id: str,
    order_summary: dict,
    suggestions: str,
) -> str:
    insight_id = str(uuid.uuid4())
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
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
        conn.commit()
    finally:
        conn.close()
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
