"""
Tenancy — tenant registration, lookup, and product enablement.

Tenants are registered in the database (ai_tenants table).
Each tenant can have one or more products enabled (ai_tenant_products).
The legacy single-user system is represented as tenant_id="legacy".
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.core.context import Product
from app.services.db_pool import pooled_cursor


# ── Sync DB operations ──────────────────────────────────────────────


def _ensure_tenant_sync(
    tenant_id: str,
    name: str,
    source_product: str,
    external_id: Optional[str] = None,
) -> dict:
    """Get or create a tenant record. Idempotent."""
    with pooled_cursor() as cur:
        cur.execute("SELECT * FROM ai_tenants WHERE id = %s", (tenant_id,))
        row = cur.fetchone()
        if row:
            return dict(row)
        cur.execute(
            """
            INSERT INTO ai_tenants (id, name, source_product, external_id, created_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            RETURNING *
            """,
            (tenant_id, name, source_product, external_id, datetime.now(timezone.utc)),
        )
        row = cur.fetchone()
        if row:
            return dict(row)
        # Race: another thread inserted first
        cur.execute("SELECT * FROM ai_tenants WHERE id = %s", (tenant_id,))
        return dict(cur.fetchone())


def _get_tenant_sync(tenant_id: str) -> Optional[dict]:
    with pooled_cursor(commit=False) as cur:
        cur.execute("SELECT * FROM ai_tenants WHERE id = %s AND enabled = true", (tenant_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def _enable_product_sync(tenant_id: str, product: str, config: Optional[dict] = None) -> None:
    """Enable a product for a tenant. Idempotent."""
    with pooled_cursor() as cur:
        cur.execute(
            """
            INSERT INTO ai_tenant_products (id, tenant_id, product, config, created_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, product) DO UPDATE SET config = COALESCE(EXCLUDED.config, ai_tenant_products.config)
            """,
            (str(uuid.uuid4()), tenant_id, product, config or {}, datetime.now(timezone.utc)),
        )


def _is_product_enabled_sync(tenant_id: str, product: str) -> bool:
    with pooled_cursor(commit=False) as cur:
        cur.execute(
            "SELECT 1 FROM ai_tenant_products WHERE tenant_id = %s AND product = %s AND enabled = true",
            (tenant_id, product),
        )
        return cur.fetchone() is not None


def _get_tenant_config_sync(tenant_id: str, product: str) -> Optional[dict]:
    with pooled_cursor(commit=False) as cur:
        cur.execute(
            "SELECT config FROM ai_tenant_products WHERE tenant_id = %s AND product = %s AND enabled = true",
            (tenant_id, product),
        )
        row = cur.fetchone()
        return dict(row["config"]) if row and row.get("config") else None


# ── Async wrappers ──────────────────────────────────────────────────


async def ensure_tenant(
    tenant_id: str, name: str, source_product: str, external_id: Optional[str] = None
) -> dict:
    return await asyncio.to_thread(_ensure_tenant_sync, tenant_id, name, source_product, external_id)


async def get_tenant(tenant_id: str) -> Optional[dict]:
    return await asyncio.to_thread(_get_tenant_sync, tenant_id)


async def enable_product(tenant_id: str, product: str, config: Optional[dict] = None) -> None:
    await asyncio.to_thread(_enable_product_sync, tenant_id, product, config)


async def is_product_enabled(tenant_id: str, product: str) -> bool:
    return await asyncio.to_thread(_is_product_enabled_sync, tenant_id, product)


async def get_tenant_config(tenant_id: str, product: str) -> Optional[dict]:
    return await asyncio.to_thread(_get_tenant_config_sync, tenant_id, product)


# ── Legacy bootstrap ────────────────────────────────────────────────


def bootstrap_legacy_tenant_sync() -> None:
    """
    Ensure the legacy single-user tenant exists with all products enabled.
    Called at startup for backward compatibility.
    """
    _ensure_tenant_sync("legacy", "Awab Personal Office", "legacy_personal")
    for p in Product:
        _enable_product_sync("legacy", p.value)
