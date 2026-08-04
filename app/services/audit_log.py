"""
Audit Log — records every agent action. Immutable append-only.
"""
import uuid
import asyncio
from datetime import datetime, timezone
import psycopg2.extras
from app.services.db_pool import pooled_cursor


def _log_sync(task_id: str | None, action: str, payload: dict, status: str) -> None:
    try:
        with pooled_cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_log (id, task_id, action, payload, status, created_at)
                VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (
                    str(uuid.uuid4()), task_id, action,
                    psycopg2.extras.Json(payload), status,
                    datetime.now(timezone.utc),
                ),
            )
    except Exception:
        # Audit log must never crash the main flow
        pass


async def log_action(task_id: str | None, action: str, payload: dict, status: str) -> None:
    await asyncio.to_thread(_log_sync, task_id, action, payload, status)


def _list_recent_sync(limit: int) -> list[dict]:
    with pooled_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT %s", (limit,))
        return [dict(r) for r in cur.fetchall()]


async def list_recent(limit: int = 20) -> list[dict]:
    return await asyncio.to_thread(_list_recent_sync, limit)
