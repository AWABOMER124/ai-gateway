"""
Olivery Report Store — persists generated operational reports.
"""
import uuid
import asyncio
from datetime import datetime, timezone
import psycopg2.extras
from app.services.db_pool import pooled_cursor


def _save_report_sync(
    task_id: str | None,
    report_type: str,
    filters: dict,
    summary: str,
    rows: list,
) -> str:
    report_id = str(uuid.uuid4())
    with pooled_cursor() as cur:
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
