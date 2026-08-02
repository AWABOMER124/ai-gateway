"""
Olivery Report Store — persists generated operational reports.
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


def _save_report_sync(
    task_id: str | None,
    report_type: str,
    filters: dict,
    summary: str,
    rows: list,
) -> str:
    report_id = str(uuid.uuid4())
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO olivery_reports
                  (id, task_id, report_type, filters, summary, rows, row_count, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    report_id, task_id, report_type,
                    psycopg2.extras.Json(filters),
                    summary,
                    psycopg2.extras.Json(rows),
                    len(rows),
                    datetime.now(timezone.utc),
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return report_id


async def save_report(
    task_id: str | None,
    report_type: str,
    filters: dict,
    summary: str,
    rows: list,
) -> str:
    return await asyncio.to_thread(
        _save_report_sync, task_id, report_type, filters, summary, rows
    )
