"""
File Processor — stores file analysis results as artifacts.
Content arrives pre-extracted from n8n (text/JSON string).
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


def _save_artifact_sync(
    task_id: str | None,
    file_name: str,
    mime_type: str,
    summary: str,
    key_points: list,
    actions: list,
    risk_notes: list,
) -> str:
    artifact_id = str(uuid.uuid4())
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO file_artifacts
                  (id, task_id, file_name, mime_type, summary, key_points, actions, risk_notes, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    artifact_id, task_id, file_name, mime_type, summary,
                    psycopg2.extras.Json(key_points),
                    psycopg2.extras.Json(actions),
                    psycopg2.extras.Json(risk_notes),
                    datetime.now(timezone.utc),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return artifact_id


async def save_artifact(
    task_id: str | None,
    file_name: str,
    mime_type: str,
    summary: str,
    key_points: list,
    actions: list,
    risk_notes: list,
) -> str:
    return await asyncio.to_thread(
        _save_artifact_sync, task_id, file_name, mime_type, summary, key_points, actions, risk_notes
    )
