"""
Olivery Edit Store — stages proposed order edits. Never writes to Olivery.
Actual write happens only from the Executor after Awab approves.
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


def _save_edit_request_sync(
    task_id: str | None,
    order_id: str,
    vals: dict,
    preview: str,
) -> str:
    request_id = str(uuid.uuid4())
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO olivery_edit_requests
                  (id, task_id, order_id, vals, preview, approval_status, created_at)
                VALUES (%s,%s,%s,%s,%s,'pending',%s)
                """,
                (
                    request_id, task_id, order_id,
                    psycopg2.extras.Json(vals), preview,
                    datetime.now(timezone.utc),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return request_id


def _get_edit_request_by_task_sync(task_id: str) -> dict | None:
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM olivery_edit_requests WHERE task_id = %s ORDER BY created_at DESC LIMIT 1",
                (task_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def _mark_executed_sync(request_id: str) -> None:
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE olivery_edit_requests SET approval_status='executed', updated_at=%s WHERE id=%s",
                (datetime.now(timezone.utc), request_id),
            )
        conn.commit()
    finally:
        conn.close()


async def save_edit_request(task_id: str | None, order_id: str, vals: dict, preview: str) -> str:
    return await asyncio.to_thread(_save_edit_request_sync, task_id, order_id, vals, preview)


async def get_edit_request_by_task(task_id: str) -> dict | None:
    return await asyncio.to_thread(_get_edit_request_by_task_sync, task_id)


async def mark_executed(request_id: str) -> None:
    await asyncio.to_thread(_mark_executed_sync, request_id)
