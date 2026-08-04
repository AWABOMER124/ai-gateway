"""
Dashboard Users — small-team login accounts. No self-signup; created via
scripts/create_dashboard_user.py.
"""
import uuid
import asyncio
from datetime import datetime, timezone
from app.services.db_pool import pooled_cursor


def _create_user_sync(email: str, password_hash: str, role: str = "member") -> str:
    user_id = str(uuid.uuid4())
    with pooled_cursor() as cur:
        cur.execute(
            "INSERT INTO dashboard_users (id, email, password_hash, role, created_at) VALUES (%s,%s,%s,%s,%s)",
            (user_id, email, password_hash, role, datetime.now(timezone.utc)),
        )
    return user_id


def _get_user_by_email_sync(email: str) -> dict | None:
    with pooled_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM dashboard_users WHERE email = %s", (email,))
        row = cur.fetchone()
        return dict(row) if row else None


def _get_user_by_id_sync(user_id: str) -> dict | None:
    with pooled_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM dashboard_users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def _list_users_sync() -> list[dict]:
    with pooled_cursor(commit=False) as cur:
        cur.execute("SELECT id, email, role, created_at, last_login_at FROM dashboard_users ORDER BY created_at")
        return [dict(r) for r in cur.fetchall()]


def _touch_last_login_sync(user_id: str) -> None:
    with pooled_cursor() as cur:
        cur.execute(
            "UPDATE dashboard_users SET last_login_at=%s WHERE id=%s",
            (datetime.now(timezone.utc), user_id),
        )


async def create_user(email: str, password_hash: str, role: str = "member") -> str:
    return await asyncio.to_thread(_create_user_sync, email, password_hash, role)


async def get_user_by_email(email: str) -> dict | None:
    return await asyncio.to_thread(_get_user_by_email_sync, email)


async def get_user_by_id(user_id: str) -> dict | None:
    return await asyncio.to_thread(_get_user_by_id_sync, user_id)


async def list_users() -> list[dict]:
    return await asyncio.to_thread(_list_users_sync)


async def touch_last_login(user_id: str) -> None:
    await asyncio.to_thread(_touch_last_login_sync, user_id)
