"""
Wasla Store Project Store — V2 versioned project persistence.

Replaces the single-draft model with a project → versions → patches hierarchy.
Each tenant has isolated projects via tenant_id filtering.
"""
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional

import psycopg2.extras
from app.services.db_pool import pooled_cursor


# ── Projects ─────────────────────────────────────────────────────────


def _create_project_sync(
    tenant_id: str,
    name: str,
    description: Optional[str] = None,
    business_type: Optional[str] = None,
    style: Optional[dict] = None,
    merchant_id: Optional[str] = None,
    created_by: str = "system",
) -> str:
    project_id = str(uuid.uuid4())
    with pooled_cursor() as cur:
        cur.execute(
            """
            INSERT INTO wasla_store_projects
                (id, tenant_id, merchant_id, name, description, business_type, style, created_by, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                project_id, tenant_id, merchant_id, name, description,
                business_type, psycopg2.extras.Json(style or {}),
                created_by, datetime.now(timezone.utc), datetime.now(timezone.utc),
            ),
        )
    return project_id


def _get_project_sync(tenant_id: str, project_id: str) -> Optional[dict]:
    with pooled_cursor(commit=False) as cur:
        cur.execute(
            "SELECT * FROM wasla_store_projects WHERE id = %s AND tenant_id = %s",
            (project_id, tenant_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _list_projects_sync(
    tenant_id: str,
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    with pooled_cursor(commit=False) as cur:
        if status:
            cur.execute(
                "SELECT * FROM wasla_store_projects WHERE tenant_id = %s AND status = %s ORDER BY updated_at DESC LIMIT %s OFFSET %s",
                (tenant_id, status, limit, offset),
            )
        else:
            cur.execute(
                "SELECT * FROM wasla_store_projects WHERE tenant_id = %s ORDER BY updated_at DESC LIMIT %s OFFSET %s",
                (tenant_id, limit, offset),
            )
        return [dict(r) for r in cur.fetchall()]


def _update_project_status_sync(tenant_id: str, project_id: str, status: str) -> None:
    with pooled_cursor() as cur:
        cur.execute(
            "UPDATE wasla_store_projects SET status = %s, updated_at = %s WHERE id = %s AND tenant_id = %s",
            (status, datetime.now(timezone.utc), project_id, tenant_id),
        )


def _update_project_style_sync(tenant_id: str, project_id: str, style: dict) -> None:
    with pooled_cursor() as cur:
        cur.execute(
            "UPDATE wasla_store_projects SET style = %s, updated_at = %s WHERE id = %s AND tenant_id = %s",
            (psycopg2.extras.Json(style), datetime.now(timezone.utc), project_id, tenant_id),
        )


# ── Versions ─────────────────────────────────────────────────────────


def _create_version_sync(
    tenant_id: str,
    project_id: str,
    version_number: int,
    payload: dict,
    prompt: Optional[str] = None,
    generation_model: Optional[str] = None,
    validation_errors: Optional[list] = None,
) -> str:
    version_id = str(uuid.uuid4())
    with pooled_cursor() as cur:
        cur.execute(
            """
            INSERT INTO wasla_store_versions
                (id, project_id, tenant_id, version_number, payload, prompt, generation_model, validation_errors, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                version_id, project_id, tenant_id, version_number,
                psycopg2.extras.Json(payload),
                prompt, generation_model,
                psycopg2.extras.Json(validation_errors or []),
                datetime.now(timezone.utc),
            ),
        )
        cur.execute(
            "UPDATE wasla_store_projects SET current_version = %s, updated_at = %s WHERE id = %s AND tenant_id = %s",
            (version_number, datetime.now(timezone.utc), project_id, tenant_id),
        )
    return version_id


def _create_next_version_sync(
    tenant_id: str,
    project_id: str,
    payload: dict,
    prompt: Optional[str] = None,
    generation_model: Optional[str] = None,
    validation_errors: Optional[list] = None,
) -> tuple[str, int]:
    """Atomically allocate the next project version under a row lock."""
    version_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with pooled_cursor() as cur:
        cur.execute(
            "SELECT current_version FROM wasla_store_projects WHERE id = %s AND tenant_id = %s FOR UPDATE",
            (project_id, tenant_id),
        )
        project = cur.fetchone()
        if not project:
            raise ValueError("Project not found")
        version_number = int(project["current_version"]) + 1
        cur.execute(
            """
            INSERT INTO wasla_store_versions
                (id, project_id, tenant_id, version_number, payload, prompt, generation_model, validation_errors, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                version_id, project_id, tenant_id, version_number,
                psycopg2.extras.Json(payload), prompt, generation_model,
                psycopg2.extras.Json(validation_errors or []), now,
            ),
        )
        cur.execute(
            "UPDATE wasla_store_projects SET current_version = %s, updated_at = %s WHERE id = %s AND tenant_id = %s",
            (version_number, now, project_id, tenant_id),
        )
    return version_id, version_number


def _get_version_sync(tenant_id: str, version_id: str) -> Optional[dict]:
    with pooled_cursor(commit=False) as cur:
        cur.execute(
            "SELECT * FROM wasla_store_versions WHERE id = %s AND tenant_id = %s",
            (version_id, tenant_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _get_latest_version_sync(tenant_id: str, project_id: str) -> Optional[dict]:
    with pooled_cursor(commit=False) as cur:
        cur.execute(
            "SELECT * FROM wasla_store_versions WHERE project_id = %s AND tenant_id = %s ORDER BY version_number DESC LIMIT 1",
            (project_id, tenant_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _list_versions_sync(tenant_id: str, project_id: str) -> list[dict]:
    with pooled_cursor(commit=False) as cur:
        cur.execute(
            "SELECT * FROM wasla_store_versions WHERE project_id = %s AND tenant_id = %s ORDER BY version_number DESC",
            (project_id, tenant_id),
        )
        return [dict(r) for r in cur.fetchall()]


def _update_version_status_sync(
    tenant_id: str,
    version_id: str,
    status: str,
    waslak_draft_id: Optional[str] = None,
    waslak_status: Optional[str] = None,
    rejection_reason: Optional[str] = None,
) -> None:
    with pooled_cursor() as cur:
        cur.execute(
            """
            UPDATE wasla_store_versions
            SET status = %s, waslak_draft_id = COALESCE(%s, waslak_draft_id),
                waslak_status = COALESCE(%s, waslak_status),
                rejection_reason = COALESCE(%s, rejection_reason),
                submitted_at = CASE WHEN %s = 'submitted' THEN %s ELSE submitted_at END
            WHERE id = %s AND tenant_id = %s
            """,
            (
                status, waslak_draft_id, waslak_status, rejection_reason,
                status, datetime.now(timezone.utc),
                version_id, tenant_id,
            ),
        )


# ── Patches ──────────────────────────────────────────────────────────


def _add_patch_sync(
    tenant_id: str,
    version_id: str,
    patch_type: str,
    patch_data: dict,
    applied_by: str = "system",
) -> str:
    patch_id = str(uuid.uuid4())
    with pooled_cursor() as cur:
        cur.execute(
            """
            INSERT INTO wasla_store_patches (id, version_id, tenant_id, patch_type, patch_data, applied_by, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                patch_id, version_id, tenant_id, patch_type,
                psycopg2.extras.Json(patch_data),
                applied_by, datetime.now(timezone.utc),
            ),
        )
    return patch_id


def _list_patches_sync(tenant_id: str, version_id: str) -> list[dict]:
    with pooled_cursor(commit=False) as cur:
        cur.execute(
            "SELECT * FROM wasla_store_patches WHERE version_id = %s AND tenant_id = %s ORDER BY created_at",
            (version_id, tenant_id),
        )
        return [dict(r) for r in cur.fetchall()]


# ── Async wrappers ───────────────────────────────────────────────────


async def create_project(**kwargs) -> str:
    return await asyncio.to_thread(_create_project_sync, **kwargs)

async def get_project(tenant_id: str, project_id: str) -> Optional[dict]:
    return await asyncio.to_thread(_get_project_sync, tenant_id, project_id)

async def list_projects(tenant_id: str, status: Optional[str] = None, limit: int = 20, offset: int = 0) -> list[dict]:
    return await asyncio.to_thread(_list_projects_sync, tenant_id, status, limit, offset)

async def update_project_status(tenant_id: str, project_id: str, status: str) -> None:
    await asyncio.to_thread(_update_project_status_sync, tenant_id, project_id, status)

async def update_project_style(tenant_id: str, project_id: str, style: dict) -> None:
    await asyncio.to_thread(_update_project_style_sync, tenant_id, project_id, style)

async def create_version(**kwargs) -> str:
    return await asyncio.to_thread(_create_version_sync, **kwargs)

async def create_next_version(**kwargs) -> tuple[str, int]:
    return await asyncio.to_thread(_create_next_version_sync, **kwargs)

async def get_version(tenant_id: str, version_id: str) -> Optional[dict]:
    return await asyncio.to_thread(_get_version_sync, tenant_id, version_id)

async def get_latest_version(tenant_id: str, project_id: str) -> Optional[dict]:
    return await asyncio.to_thread(_get_latest_version_sync, tenant_id, project_id)

async def list_versions(tenant_id: str, project_id: str) -> list[dict]:
    return await asyncio.to_thread(_list_versions_sync, tenant_id, project_id)

async def update_version_status(tenant_id: str, version_id: str, **kwargs) -> None:
    await asyncio.to_thread(_update_version_status_sync, tenant_id, version_id, **kwargs)

async def add_patch(**kwargs) -> str:
    return await asyncio.to_thread(_add_patch_sync, **kwargs)

async def list_patches(tenant_id: str, version_id: str) -> list[dict]:
    return await asyncio.to_thread(_list_patches_sync, tenant_id, version_id)
