"""
Waslak Draft Store — stages generated store drafts. Never submits to Waslak.
Actual submission happens only from the Executor after Awab approves.
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


def _save_draft_sync(
    task_id: str | None,
    prompt: str,
    business_type: str | None,
    payload: dict,
    validation_errors: list,
) -> str:
    draft_id = str(uuid.uuid4())
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO waslak_store_drafts
                  (id, task_id, prompt, business_type, payload, validation_errors,
                   approval_status, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,'pending',%s)
                """,
                (
                    draft_id, task_id, prompt, business_type,
                    psycopg2.extras.Json(payload),
                    psycopg2.extras.Json(validation_errors),
                    datetime.now(timezone.utc),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return draft_id


def _get_draft_sync(draft_id: str) -> dict | None:
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM waslak_store_drafts WHERE id = %s", (draft_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def _get_draft_by_task_sync(task_id: str) -> dict | None:
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM waslak_store_drafts WHERE task_id = %s ORDER BY created_at DESC LIMIT 1",
                (task_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def _update_remote_status_sync(
    draft_id: str,
    waslak_draft_id: str | None,
    waslak_status: str | None,
    merchant_id: str | None,
    rejection_reason: str | None,
    approval_status: str | None = None,
) -> None:
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE waslak_store_drafts
                SET waslak_draft_id=%s, waslak_status=%s, merchant_id=%s, rejection_reason=%s,
                    approval_status=COALESCE(%s, approval_status), updated_at=%s
                WHERE id=%s
                """,
                (
                    waslak_draft_id, waslak_status, merchant_id, rejection_reason,
                    approval_status, datetime.now(timezone.utc), draft_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _mark_execution_failed_sync(draft_id: str, reason: str) -> None:
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE waslak_store_drafts SET approval_status='execution_failed', rejection_reason=%s, updated_at=%s WHERE id=%s",
                (reason, datetime.now(timezone.utc), draft_id),
            )
        conn.commit()
    finally:
        conn.close()


async def save_draft(
    task_id: str | None,
    prompt: str,
    business_type: str | None,
    payload: dict,
    validation_errors: list,
) -> str:
    return await asyncio.to_thread(
        _save_draft_sync, task_id, prompt, business_type, payload, validation_errors
    )


async def get_draft(draft_id: str) -> dict | None:
    return await asyncio.to_thread(_get_draft_sync, draft_id)


async def get_draft_by_task(task_id: str) -> dict | None:
    return await asyncio.to_thread(_get_draft_by_task_sync, task_id)


async def update_remote_status(
    local_id: str,
    waslak_draft_id: str | None,
    waslak_status: str | None,
    merchant_id: str | None,
    rejection_reason: str | None,
    approval_status: str | None = None,
) -> None:
    await asyncio.to_thread(
        _update_remote_status_sync, local_id, waslak_draft_id, waslak_status,
        merchant_id, rejection_reason, approval_status,
    )


async def mark_execution_failed(draft_id: str, reason: str) -> None:
    await asyncio.to_thread(_mark_execution_failed_sync, draft_id, reason)
