"""
Email Store — saves and retrieves email drafts. Never sends.
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
    subject: str,
    to_email: str,
    draft_body: str,
    summary: str,
    risk_notes: list,
) -> str:
    draft_id = str(uuid.uuid4())
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO email_drafts
                  (id, task_id, to_email, subject, draft_body, summary, risk_notes,
                   approval_status, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'pending',%s)
                """,
                (
                    draft_id, task_id, to_email, subject, draft_body,
                    summary, psycopg2.extras.Json(risk_notes),
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
            cur.execute("SELECT * FROM email_drafts WHERE id = %s", (draft_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def _get_draft_by_task_sync(task_id: str) -> dict | None:
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM email_drafts WHERE task_id = %s ORDER BY created_at DESC LIMIT 1",
                (task_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def _approve_draft_sync(draft_id: str) -> None:
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE email_drafts SET approval_status='approved', updated_at=%s WHERE id=%s",
                (datetime.now(timezone.utc), draft_id),
            )
        conn.commit()
    finally:
        conn.close()


async def save_draft(
    task_id: str | None,
    subject: str,
    to_email: str,
    draft_body: str,
    summary: str,
    risk_notes: list,
) -> str:
    return await asyncio.to_thread(
        _save_draft_sync, task_id, subject, to_email, draft_body, summary, risk_notes
    )


async def get_draft(draft_id: str) -> dict | None:
    return await asyncio.to_thread(_get_draft_sync, draft_id)


async def get_draft_by_task(task_id: str) -> dict | None:
    return await asyncio.to_thread(_get_draft_by_task_sync, task_id)


async def approve_draft(draft_id: str) -> None:
    await asyncio.to_thread(_approve_draft_sync, draft_id)
