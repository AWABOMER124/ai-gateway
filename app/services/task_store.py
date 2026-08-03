"""
Task Store — CRUD for ai_tasks, ai_task_steps, ai_reviews.
Uses psycopg2 sync wrapped in asyncio.to_thread.
"""
import uuid
import asyncio
from datetime import datetime, timezone
import psycopg2.extras
from app.services.db_pool import pooled_cursor


def _create_task_sync(user_id: str, channel: str, message: str, plan: dict, channel_ref: str = "") -> str:
    task_id = str(uuid.uuid4())
    with pooled_cursor() as cur:
        cur.execute(
            """
            INSERT INTO ai_tasks (id, user_id, channel, channel_ref, message, intent, assigned_agent,
                                  risk_level, needs_approval, plan, status, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s)
            """,
            (
                task_id, user_id, channel, channel_ref or None, message,
                plan.get("intent"), plan.get("assigned_agent"),
                plan.get("risk_level"), plan.get("needs_approval", False),
                psycopg2.extras.Json(plan),
                datetime.now(timezone.utc),
            ),
        )
    return task_id


def _get_task_sync(task_id: str) -> dict | None:
    with pooled_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM ai_tasks WHERE id = %s", (task_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def _get_pending_task_sync(channel_ref: str) -> dict | None:
    with pooled_cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT * FROM ai_tasks
            WHERE channel_ref = %s AND status = 'awaiting_confirmation'
            ORDER BY created_at DESC LIMIT 1
            """,
            (channel_ref,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _update_task_status_sync(task_id: str, status: str, output: dict | None = None) -> None:
    with pooled_cursor() as cur:
        if output is not None:
            cur.execute(
                "UPDATE ai_tasks SET status=%s, output=%s, updated_at=%s WHERE id=%s",
                (status, psycopg2.extras.Json(output), datetime.now(timezone.utc), task_id),
            )
        else:
            cur.execute(
                "UPDATE ai_tasks SET status=%s, updated_at=%s WHERE id=%s",
                (status, datetime.now(timezone.utc), task_id),
            )


def _save_review_sync(task_id: str, review: dict) -> None:
    with pooled_cursor() as cur:
        cur.execute(
            """
            INSERT INTO ai_reviews (id, task_id, approved, final_answer,
                                    issues, needs_user_confirmation, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (task_id) DO UPDATE
              SET approved=EXCLUDED.approved,
                  final_answer=EXCLUDED.final_answer,
                  issues=EXCLUDED.issues,
                  needs_user_confirmation=EXCLUDED.needs_user_confirmation
            """,
            (
                str(uuid.uuid4()), task_id,
                review.get("approved", False),
                review.get("final_answer", ""),
                psycopg2.extras.Json(review.get("issues", [])),
                review.get("needs_user_confirmation", False),
                datetime.now(timezone.utc),
            ),
        )


# Async wrappers
async def create_task(user_id: str, channel: str, message: str, plan: dict, channel_ref: str = "") -> str:
    return await asyncio.to_thread(_create_task_sync, user_id, channel, message, plan, channel_ref)


async def get_task(task_id: str) -> dict | None:
    return await asyncio.to_thread(_get_task_sync, task_id)


async def get_pending_task(channel_ref: str) -> dict | None:
    return await asyncio.to_thread(_get_pending_task_sync, channel_ref)


async def update_task_status(task_id: str, status: str, output: dict | None = None) -> None:
    await asyncio.to_thread(_update_task_status_sync, task_id, status, output)


async def save_review(task_id: str, review: dict) -> None:
    await asyncio.to_thread(_save_review_sync, task_id, review)
