"""
Wasla Store Tools — tools for store generation and management.

Store Architect V2 tools for generating, validating, and submitting
store drafts through the Waslak platform.

Tools registered here:
- wasla.store.generate     — generate a store draft (LOW_RISK_WRITE)
- wasla.store.submit       — submit draft to Waslak (SENSITIVE_WRITE)
- wasla.merchants.list     — list merchants (READ_ONLY)
- wasla.merchants.insights — get merchant insights (READ_ONLY)
- wasla.store.get_draft    — get a store draft (READ_ONLY)
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
    key="wasla.store.generate",
    version="2.0.0",
    product="wasla",
    description="توليد مسودة متجر بالذكاء الاصطناعي — Generate an AI store draft",
    risk_level=RiskLevel.LOW_RISK_WRITE,
    required_permissions=["store.generate"],
    input_schema={
        "type": "object",
        "properties": {
            "merchant_description": {
                "type": "string",
                "description": "وصف نشاط التاجر ومنتجاته",
                "maxLength": 2000,
            },
            "merchant_name": {"type": "string", "maxLength": 120},
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
async def generate_store_draft(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_wasla_adapter()
    result = await adapter.generate_store_draft(
        ctx,
        merchant_description=params["merchant_description"],
        merchant_name=params.get("merchant_name"),
        style_preferences=params.get("style_preferences"),
    )
    return result


@register_tool(
    key="wasla.store.submit",
    version="2.0.0",
    product="wasla",
    description="تقديم المسودة لمنصة وصلة — Submit draft to Waslak platform",
    risk_level=RiskLevel.SENSITIVE_WRITE,
    required_permissions=["store.submit"],
    input_schema={
        "type": "object",
        "properties": {
            "draft_data": {"type": "object", "description": "The store draft to submit"},
            "merchant_id": {"type": "string"},
        },
        "required": ["draft_data"],
    },
    idempotency_required=True,
    timeout_seconds=30,
    allowed_products=["wasla", "legacy_personal"],
)
async def submit_store_draft(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_wasla_adapter()
    result = await adapter.submit_draft_to_waslak(
        ctx,
        draft_data=params["draft_data"],
        merchant_id=params.get("merchant_id"),
    )
    return result


@register_tool(
    key="wasla.store.get_draft",
    version="2.0.0",
    product="wasla",
    description="جلب مسودة متجر — Get a store draft by local ID",
    risk_level=RiskLevel.READ_ONLY,
    required_permissions=["store.view"],
    input_schema={
        "type": "object",
        "properties": {
            "local_id": {"type": "string"},
        },
        "required": ["local_id"],
    },
    timeout_seconds=15,
    allowed_products=["wasla", "legacy_personal"],
)
async def get_store_draft(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_wasla_adapter()
    return await adapter.get_draft(ctx, params["local_id"])


@register_tool(
    key="wasla.merchants.list",
    version="1.0.0",
    product="wasla",
    description="قائمة التجار — List merchants",
    risk_level=RiskLevel.READ_ONLY,
    required_permissions=["merchants.view"],
    input_schema={
        "type": "object",
        "properties": {
            "page": {"type": "integer", "default": 1},
            "per_page": {"type": "integer", "default": 20, "maximum": 100},
        },
    },
    timeout_seconds=10,
    allowed_products=["wasla", "legacy_personal"],
)
async def list_merchants(ctx: ExecutionContext, params: dict[str, Any]) -> dict:
    adapter = _get_wasla_adapter()
    return await adapter.list_merchants(
        ctx, page=params.get("page", 1), per_page=params.get("per_page", 20)
    )


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
