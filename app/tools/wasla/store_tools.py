"""
Wasla Store Tools V2 — tools for store project lifecycle.

Store Architect V2: projects with versioned drafts, incremental patches,
and submission to the Waslak platform.

Tools registered here:
- wasla.store.create_project  — create a new store project (LOW_RISK_WRITE)
- wasla.store.regenerate      — generate a new version (LOW_RISK_WRITE)
- wasla.store.patch           — apply incremental edit (LOW_RISK_WRITE)
- wasla.store.submit          — submit to Waslak platform (SENSITIVE_WRITE)
- wasla.store.status          — check submission status (READ_ONLY)
- wasla.projects.list         — list store projects (READ_ONLY)
- wasla.projects.get          — get project details (READ_ONLY)
- wasla.merchants.list        — list merchants (READ_ONLY)
- wasla.merchants.insights    — get merchant insights (READ_ONLY)
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.context import ExecutionContext
from app.core.policies import RiskLevel
from app.tools.registry import register_tool

logger = logging.getLogger(__name__)


def _get_wasla_adapter():
    from app.integrations.wasla.adapter import WaslaAdapter
    return WaslaAdapter()


@register_tool(
    key="wasla.store.create_project",
    version="2.0.0",
    product="wasla",
    description="إنشاء مشروع متجر جديد بالذكاء الاصطناعي — Create a new AI store project",
    risk_level=RiskLevel.LOW_RISK_WRITE,
    required_permissions=["store.generate"],
    input_schema={
        "type": "object",
        "properties": {
            "merchant_description": {"type": "string", "maxLength": 2000},
            "merchant_name": {"type": "string", "maxLength": 120},
            "business_type": {"type": "string", "enum": ["ecommerce", "restaurant", "landing_page"]},
            "style_preferences": {
                "type": "object",
                "properties": {
                    "primary_color": {"type": "string", "pattern": "^#[0-9a-fA-F]{6}$"},
                    "style": {"type": "string", "enum": ["modern", "classic", "minimal", "bold"]},
                },
            },
        },
        "required": ["merchant_description"],
    },
    timeout_seconds=60,
    allowed_products=["wasla", "legacy_personal"],
)
async def create_store_project(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_wasla_adapter()
    return await adapter.create_store_project(
        ctx,
        merchant_description=params["merchant_description"],
        merchant_name=params.get("merchant_name"),
        business_type=params.get("business_type"),
        style_preferences=params.get("style_preferences"),
    )


@register_tool(
    key="wasla.store.regenerate",
    version="2.0.0",
    product="wasla",
    description="توليد نسخة جديدة لمشروع متجر — Regenerate a new store version",
    risk_level=RiskLevel.LOW_RISK_WRITE,
    required_permissions=["store.generate"],
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "prompt": {"type": "string", "maxLength": 2000},
            "style_preferences": {"type": "object"},
        },
        "required": ["project_id"],
    },
    timeout_seconds=60,
    allowed_products=["wasla", "legacy_personal"],
)
async def regenerate_version(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_wasla_adapter()
    return await adapter.regenerate_version(
        ctx,
        project_id=params["project_id"],
        prompt=params.get("prompt"),
        style_preferences=params.get("style_preferences"),
    )


@register_tool(
    key="wasla.store.patch",
    version="2.0.0",
    product="wasla",
    description="تعديل تدريجي على مشروع متجر — Apply incremental patch to store project",
    risk_level=RiskLevel.LOW_RISK_WRITE,
    required_permissions=["store.generate"],
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "patch_type": {
                "type": "string",
                "enum": ["add_category", "remove_category", "edit_product", "edit_style", "edit_info", "ai_refine"],
            },
            "patch_data": {"type": "object"},
        },
        "required": ["project_id", "patch_type", "patch_data"],
    },
    timeout_seconds=60,
    allowed_products=["wasla", "legacy_personal"],
)
async def apply_patch(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_wasla_adapter()
    return await adapter.apply_patch(
        ctx,
        project_id=params["project_id"],
        patch_type=params["patch_type"],
        patch_data=params["patch_data"],
    )


@register_tool(
    key="wasla.store.submit",
    version="2.0.0",
    product="wasla",
    description="تقديم مشروع المتجر لمنصة وصلة — Submit store project to Waslak platform",
    risk_level=RiskLevel.SENSITIVE_WRITE,
    required_permissions=["store.submit"],
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "version_id": {"type": "string"},
        },
        "required": ["project_id"],
    },
    idempotency_required=True,
    timeout_seconds=30,
    allowed_products=["wasla", "legacy_personal"],
)
async def submit_store(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_wasla_adapter()
    return await adapter.submit_to_waslak(
        ctx,
        project_id=params["project_id"],
        version_id=params.get("version_id"),
    )


@register_tool(
    key="wasla.store.status",
    version="2.0.0",
    product="wasla",
    description="التحقق من حالة تقديم المتجر — Check store submission status",
    risk_level=RiskLevel.READ_ONLY,
    required_permissions=["store.view"],
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "version_id": {"type": "string"},
        },
        "required": ["project_id"],
    },
    timeout_seconds=15,
    allowed_products=["wasla", "legacy_personal"],
)
async def check_status(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_wasla_adapter()
    return await adapter.check_submission_status(
        ctx,
        project_id=params["project_id"],
        version_id=params.get("version_id"),
    )


@register_tool(
    key="wasla.projects.list",
    version="2.0.0",
    product="wasla",
    description="قائمة مشاريع المتاجر — List store projects",
    risk_level=RiskLevel.READ_ONLY,
    required_permissions=["store.view"],
    input_schema={
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["draft", "submitted", "approved", "rejected", "live"]},
            "limit": {"type": "integer", "default": 20, "maximum": 50},
        },
    },
    timeout_seconds=10,
    allowed_products=["wasla", "legacy_personal"],
)
async def list_projects(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_wasla_adapter()
    projects = await adapter.list_projects(
        ctx, status=params.get("status"), limit=params.get("limit", 20)
    )
    return {
        "count": len(projects),
        "projects": [
            {
                "id": p["id"],
                "name": p["name"],
                "status": p["status"],
                "current_version": p["current_version"],
                "business_type": p.get("business_type"),
            }
            for p in projects
        ],
    }


@register_tool(
    key="wasla.projects.get",
    version="2.0.0",
    product="wasla",
    description="تفاصيل مشروع متجر — Get store project details",
    risk_level=RiskLevel.READ_ONLY,
    required_permissions=["store.view"],
    input_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
        },
        "required": ["project_id"],
    },
    timeout_seconds=10,
    allowed_products=["wasla", "legacy_personal"],
)
async def get_project(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_wasla_adapter()
    project = await adapter.get_project_detail(ctx, params["project_id"])
    if not project:
        return {"found": False}
    return {"found": True, "project": project}


@register_tool(
    key="wasla.merchants.list",
    version="1.0.0",
    product="wasla",
    description="قائمة التجار — List merchants",
    risk_level=RiskLevel.READ_ONLY,
    required_permissions=["merchants.view"],
    input_schema={"type": "object", "properties": {}},
    timeout_seconds=10,
    allowed_products=["wasla", "legacy_personal"],
)
async def list_merchants(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_wasla_adapter()
    return await adapter.list_merchants(ctx)


@register_tool(
    key="wasla.merchants.insights",
    version="1.0.0",
    product="wasla",
    description="تحليلات ذكية للتاجر — AI-generated merchant insights",
    risk_level=RiskLevel.READ_ONLY,
    required_permissions=["merchants.view"],
    input_schema={
        "type": "object",
        "properties": {
            "merchant_id": {"type": "string"},
        },
        "required": ["merchant_id"],
    },
    timeout_seconds=30,
    allowed_products=["wasla", "legacy_personal"],
)
async def get_merchant_insights(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_wasla_adapter()
    return await adapter.get_merchant_insights(ctx, params["merchant_id"])
