"""
Integration API Keys — scoped, revocable keys for external products to
connect to this gateway. Only a SHA-256 hash is ever persisted; the raw key
is returned once, at issue time, by issue_key().
"""
import uuid
import asyncio
from datetime import datetime, timezone
import psycopg2.extras
from app.services.db_pool import pooled_cursor
from app.services.security import generate_api_key, hash_token


def _issue_key_sync(name: str, scopes: list[str], created_by: str | None) -> tuple[str, dict]:
    full_key, key_prefix, key_hash = generate_api_key()
    key_id = str(uuid.uuid4())
    with pooled_cursor() as cur:
        cur.execute(
            """
            INSERT INTO integration_api_keys (id, name, key_prefix, key_hash, scopes, created_by, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (key_id, name, key_prefix, key_hash, psycopg2.extras.Json(scopes), created_by, datetime.now(timezone.utc)),
        )
        cur.execute("SELECT * FROM integration_api_keys WHERE id = %s", (key_id,))
        row = dict(cur.fetchone())
    return full_key, row


def _get_key_by_token_sync(token: str) -> dict | None:
    key_hash = hash_token(token)
    with pooled_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM integration_api_keys WHERE key_hash = %s", (key_hash,))
        row = cur.fetchone()
        return dict(row) if row else None


def _list_keys_sync() -> list[dict]:
    with pooled_cursor(commit=False) as cur:
        cur.execute(
            "SELECT id, name, key_prefix, scopes, created_by, revoked_at, last_used_at, created_at "
            "FROM integration_api_keys ORDER BY created_at DESC"
        )
        return [dict(r) for r in cur.fetchall()]


def _revoke_key_sync(key_id: str) -> None:
    with pooled_cursor() as cur:
        cur.execute(
            "UPDATE integration_api_keys SET revoked_at=%s WHERE id=%s AND revoked_at IS NULL",
            (datetime.now(timezone.utc), key_id),
        )


def _touch_last_used_sync(key_id: str) -> None:
    with pooled_cursor() as cur:
        cur.execute(
            "UPDATE integration_api_keys SET last_used_at=%s WHERE id=%s",
            (datetime.now(timezone.utc), key_id),
        )


async def issue_key(name: str, scopes: list[str], created_by: str | None) -> tuple[str, dict]:
    return await asyncio.to_thread(_issue_key_sync, name, scopes, created_by)


async def get_key_by_token(token: str) -> dict | None:
    return await asyncio.to_thread(_get_key_by_token_sync, token)


async def list_keys() -> list[dict]:
    return await asyncio.to_thread(_list_keys_sync)


async def revoke_key(key_id: str) -> None:
    await asyncio.to_thread(_revoke_key_sync, key_id)


async def touch_last_used(key_id: str) -> None:
    await asyncio.to_thread(_touch_last_used_sync, key_id)
