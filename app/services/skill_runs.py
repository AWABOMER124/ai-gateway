"""
Skill Runs — persists health-check and capability-test results for the
skill readiness dashboard page (app/services/skill_registry.py).
"""
import uuid
import asyncio
from datetime import datetime, timezone
from app.services.db_pool import pooled_cursor


def _record_run_sync(
    skill_code: str,
    check_type: str,
    passed: bool,
    score: float | None,
    summary: str,
    output_excerpt: str,
    triggered_by: str | None,
) -> str:
    run_id = str(uuid.uuid4())
    with pooled_cursor() as cur:
        cur.execute(
            """
            INSERT INTO skill_test_runs
              (id, skill_code, check_type, passed, score, summary, output_excerpt, triggered_by, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (run_id, skill_code, check_type, passed, score, summary, output_excerpt[:2000] if output_excerpt else None,
             triggered_by, datetime.now(timezone.utc)),
        )
    return run_id


def _list_recent_sync(skill_code: str | None, limit: int) -> list[dict]:
    with pooled_cursor(commit=False) as cur:
        if skill_code:
            cur.execute(
                "SELECT * FROM skill_test_runs WHERE skill_code = %s ORDER BY created_at DESC LIMIT %s",
                (skill_code, limit),
            )
        else:
            cur.execute("SELECT * FROM skill_test_runs ORDER BY created_at DESC LIMIT %s", (limit,))
        return [dict(r) for r in cur.fetchall()]


def _get_latest_per_skill_sync() -> list[dict]:
    with pooled_cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (skill_code, check_type) *
            FROM skill_test_runs
            ORDER BY skill_code, check_type, created_at DESC
            """
        )
        return [dict(r) for r in cur.fetchall()]


async def record_run(
    skill_code: str,
    check_type: str,
    passed: bool,
    score: float | None,
    summary: str,
    output_excerpt: str,
    triggered_by: str | None = None,
) -> str:
    return await asyncio.to_thread(
        _record_run_sync, skill_code, check_type, passed, score, summary, output_excerpt, triggered_by
    )


async def list_recent(skill_code: str | None = None, limit: int = 20) -> list[dict]:
    return await asyncio.to_thread(_list_recent_sync, skill_code, limit)


async def get_latest_per_skill() -> list[dict]:
    return await asyncio.to_thread(_get_latest_per_skill_sync)
