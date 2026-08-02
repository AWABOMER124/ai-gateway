"""
Task Store — CRUD for ai_tasks, ai_task_steps, ai_reviews.
Uses psycopg2 sync wrapped in asyncio.to_thread.
"""
import os
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Any
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


def _create_task_sync(user_id: str, channel: str, message: str, plan: dict, channel_ref: str = "") -> str:
    task_id = str(uuid.uuid4())
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
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
        conn.commit()
    finally:
        conn.close()
    return task_id


def _get_task_sync(task_id: str) -> dict | None:
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM ai_tasks WHERE id = %s", (task_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def _get_pending_task_sync(channel_ref: str) -> dict | None:
    conn = _get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
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
    finally:
        conn.close()


def _update_task_status_sync(task_id: str, status: str, output: dict | None = None) -> None:
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
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
        conn.commit()
    finally:
        conn.close()


def _save_review_sync(task_id: str, review: dict) -> None:
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
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
        conn.commit()
    finally:
        conn.close()


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
