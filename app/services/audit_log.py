"""
Audit Log — records every agent action. Immutable append-only.
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


def _log_sync(task_id: str | None, action: str, payload: dict, status: str) -> None:
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
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
        conn.commit()
    except Exception:
        # Audit log must never crash the main flow
        pass
    finally:
        conn.close()


async def log_action(task_id: str | None, action: str, payload: dict, status: str) -> None:
    await asyncio.to_thread(_log_sync, task_id, action, payload, status)
