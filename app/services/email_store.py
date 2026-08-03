"""
Email Store — saves and retrieves email drafts. Never sends.
"""
import uuid
import asyncio
from datetime import datetime, timezone
import psycopg2.extras
from app.services.db_pool import pooled_cursor


def _save_draft_sync(
    task_id: str | None,
    subject: str,
    to_email: str,
    draft_body: str,
    summary: str,
    risk_notes: list,
) -> str:
    draft_id = str(uuid.uuid4())
    with pooled_cursor() as cur:
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
    return draft_id


def _get_draft_sync(draft_id: str) -> dict | None:
    with pooled_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM email_drafts WHERE id = %s", (draft_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def _get_draft_by_task_sync(task_id: str) -> dict | None:
    with pooled_cursor(commit=False) as cur:
        cur.execute(
            "SELECT * FROM email_drafts WHERE task_id = %s ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _approve_draft_sync(draft_id: str) -> None:
    with pooled_cursor() as cur:
        cur.execute(
            "UPDATE email_drafts SET approval_status='approved', updated_at=%s WHERE id=%s",
            (datetime.now(timezone.utc), draft_id),
        )


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
