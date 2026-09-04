"""
Wasla Adapter — multi-tenant integration with Waslak Merchant OS.

Handles two paths:
1. Legacy: uses env-based credentials (WASLAK_BASE_URL, WASLAK_API_KEY)
2. Multi-tenant: uses per-tenant credentials from wasla_tenant_config table

Store Project V2: manages projects with versioned drafts and incremental patches.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

from app.core.context import ExecutionContext
from app.core.errors import ToolExecutionFailed

logger = logging.getLogger(__name__)


class WaslaAdapter:
    """
    Multi-tenant Wasla adapter with Store Project V2 support.
    """

    async def _get_client_config(self, ctx: ExecutionContext) -> tuple[str, str]:
        if ctx.tenant_id == "legacy":
            base_url = os.getenv("WASLAK_BASE_URL", "")
            api_key = os.getenv("WASLAK_API_KEY", "")
            if not base_url or not api_key:
                raise ToolExecutionFailed("wasla", "Waslak not configured: missing WASLAK_BASE_URL or WASLAK_API_KEY")
            return base_url.rstrip("/"), api_key

        from app.services.db_pool import pooled_cursor
        import asyncio

        def _fetch():
            with pooled_cursor(commit=False) as cur:
                cur.execute(
                    "SELECT waslak_base_url, waslak_api_key_encrypted FROM wasla_tenant_config WHERE tenant_id = %s AND enabled = true",
                    (ctx.tenant_id,),
                )
                return cur.fetchone()

        row = await asyncio.to_thread(_fetch)
        if not row:
            raise ToolExecutionFailed("wasla", f"Wasla not configured for tenant: {ctx.tenant_id}")

        return row["waslak_base_url"].rstrip("/"), row["waslak_api_key_encrypted"]

    async def _waslak_request(
        self,
        ctx: ExecutionContext,
        method: str,
        path: str,
        json_body: Optional[dict] = None,
    ) -> dict:
        base_url, api_key = await self._get_client_config(ctx)

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.request(
                method=method,
                url=f"{base_url}{path}",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=json_body,
            )

        try:
            body = r.json()
        except Exception:
            body = {}

        if r.status_code == 429:
            raise ToolExecutionFailed("wasla", "Waslak rate limit exceeded (30/hour)")
        if r.status_code == 422:
            raise ToolExecutionFailed("wasla", f"Waslak validation error: {body.get('message', 'Unknown')}")
        if r.status_code >= 400:
            raise ToolExecutionFailed("wasla", f"Waslak API error {r.status_code}: {body.get('message', '')}")

        return body.get("data", body)

    # ── Store Project V2 ─────────────────────────────────────────────

    async def create_store_project(
        self,
        ctx: ExecutionContext,
        merchant_description: str,
        merchant_name: Optional[str] = None,
        business_type: Optional[str] = None,
        style_preferences: Optional[dict] = None,
    ) -> dict[str, Any]:
        from app.agents.waslak_agent import generate_store_draft
        from app.services import wasla_project_store as store

        payload = await generate_store_draft(merchant_description, business_type)
        validation_errors = payload.pop("_validation_errors", [])
        store_name = payload.get("name", merchant_name or "متجر جديد")

        project_id = await store.create_project(
            tenant_id=ctx.tenant_id,
            name=store_name,
            description=merchant_description,
            business_type=business_type,
            style=style_preferences or {},
            created_by=ctx.actor.id,
        )

        version_id = await store.create_version(
            tenant_id=ctx.tenant_id,
            project_id=project_id,
            version_number=1,
            payload=payload,
            prompt=merchant_description,
            generation_model=os.getenv("CHAT_MODEL", "gpt-4.1-mini"),
            validation_errors=validation_errors,
        )

        return {
            "project_id": project_id,
            "version_id": version_id,
            "version_number": 1,
            "name": store_name,
            "payload": payload,
            "validation_errors": validation_errors,
            "status": "draft",
        }

    async def regenerate_version(
        self,
        ctx: ExecutionContext,
        project_id: str,
        prompt: Optional[str] = None,
        style_preferences: Optional[dict] = None,
    ) -> dict[str, Any]:
        from app.agents.waslak_agent import generate_store_draft
        from app.services import wasla_project_store as store

        project = await store.get_project(ctx.tenant_id, project_id)
        if not project:
            raise ToolExecutionFailed("wasla", f"Project not found: {project_id}")

        generation_prompt = prompt or project.get("description", "")
        if not generation_prompt:
            raise ToolExecutionFailed("wasla", "No prompt available for regeneration")

        payload = await generate_store_draft(generation_prompt, project.get("business_type"))
        validation_errors = payload.pop("_validation_errors", [])

        new_version_number = project["current_version"] + 1

        if style_preferences:
            await store.update_project_style(ctx.tenant_id, project_id, style_preferences)

        version_id = await store.create_version(
            tenant_id=ctx.tenant_id,
            project_id=project_id,
            version_number=new_version_number,
            payload=payload,
            prompt=generation_prompt,
            generation_model=os.getenv("CHAT_MODEL", "gpt-4.1-mini"),
            validation_errors=validation_errors,
        )

        return {
            "project_id": project_id,
            "version_id": version_id,
            "version_number": new_version_number,
            "payload": payload,
            "validation_errors": validation_errors,
        }

    async def apply_patch(
        self,
        ctx: ExecutionContext,
        project_id: str,
        patch_type: str,
        patch_data: dict,
    ) -> dict[str, Any]:
        from app.services import wasla_project_store as store
        import copy

        project = await store.get_project(ctx.tenant_id, project_id)
        version = await store.get_latest_version(ctx.tenant_id, project_id)
        if not project or not version:
            raise ToolExecutionFailed("wasla", f"No versions found for project: {project_id}")

        payload = copy.deepcopy(version.get("payload", {}))
        validation_errors = []

        if patch_type == "add_category":
            cats = payload.get("categories", [])
            cats.append(patch_data.get("category", {}))
            payload["categories"] = cats

        elif patch_type == "remove_category":
            cat_name = patch_data.get("category_name", "")
            payload["categories"] = [
                c for c in payload.get("categories", [])
                if c.get("name") != cat_name
            ]

        elif patch_type == "edit_product":
            cat_name = patch_data.get("category_name", "")
            product_name = patch_data.get("product_name", "")
            updates = patch_data.get("updates", {})
            for cat in payload.get("categories", []):
                if cat.get("name") == cat_name:
                    for prod in cat.get("products", []):
                        if prod.get("name") == product_name:
                            prod.update(updates)
                            break

        elif patch_type == "edit_style":
            if "primaryColor" in patch_data:
                payload["primaryColor"] = patch_data["primaryColor"]
            for field in ("name", "description", "slogan", "welcomeText"):
                if field in patch_data:
                    payload[field] = patch_data[field]

        elif patch_type == "edit_info":
            for field in ("name", "description", "slogan", "welcomeText"):
                if field in patch_data:
                    payload[field] = patch_data[field]

        elif patch_type == "ai_refine":
            from app.agents.waslak_agent import generate_store_draft
            refinement_prompt = patch_data.get("prompt", "")
            if not refinement_prompt.strip():
                raise ToolExecutionFailed("wasla", "AI refinement prompt is required")
            original_prompt = version.get("prompt", "")
            combined = f"{original_prompt}\n\nتعديلات مطلوبة: {refinement_prompt}"
            refined = await generate_store_draft(combined, payload.get("business_type"))
            validation_errors = refined.pop("_validation_errors", [])
            payload = refined
        else:
            raise ToolExecutionFailed("wasla", f"Unsupported patch type: {patch_type}")

        new_version_number = project["current_version"] + 1
        new_version_id = await store.create_version(
            tenant_id=ctx.tenant_id,
            project_id=project_id,
            version_number=new_version_number,
            payload=payload,
            prompt=version.get("prompt"),
            generation_model=version.get("generation_model"),
            validation_errors=validation_errors,
        )
        patch_id = await store.add_patch(
            tenant_id=ctx.tenant_id,
            version_id=new_version_id,
            patch_type=patch_type,
            patch_data=patch_data,
            applied_by=ctx.actor.id,
        )

        return {
            "patch_id": patch_id,
            "patch_type": patch_type,
            "version_id": new_version_id,
            "version_number": new_version_number,
            "payload": payload,
        }

    async def restore_version(
        self,
        ctx: ExecutionContext,
        project_id: str,
        source_version_id: str,
    ) -> dict[str, Any]:
        """Restore without mutation by copying an owned historical version into a new head."""
        from app.services import wasla_project_store as store
        import copy

        project = await store.get_project(ctx.tenant_id, project_id)
        source = await store.get_version(ctx.tenant_id, source_version_id)
        if not project or not source or str(source.get("project_id")) != project_id:
            raise ToolExecutionFailed("wasla", "Project version not found")

        new_version_number = project["current_version"] + 1
        payload = copy.deepcopy(source.get("payload", {}))
        version_id = await store.create_version(
            tenant_id=ctx.tenant_id,
            project_id=project_id,
            version_number=new_version_number,
            payload=payload,
            prompt=source.get("prompt"),
            generation_model=source.get("generation_model"),
            validation_errors=source.get("validation_errors", []),
        )
        patch_id = await store.add_patch(
            tenant_id=ctx.tenant_id,
            version_id=version_id,
            patch_type="restore_version",
            patch_data={"source_version_id": source_version_id},
            applied_by=ctx.actor.id,
        )
        return {
            "project_id": project_id,
            "version_id": version_id,
            "version_number": new_version_number,
            "restored_from_version_id": source_version_id,
            "patch_id": patch_id,
            "payload": payload,
            "validation_errors": source.get("validation_errors", []),
        }

    async def submit_to_waslak(
        self,
        ctx: ExecutionContext,
        project_id: str,
        version_id: Optional[str] = None,
    ) -> dict[str, Any]:
        from app.services import wasla_project_store as store

        if version_id:
            version = await store.get_version(ctx.tenant_id, version_id)
        else:
            version = await store.get_latest_version(ctx.tenant_id, project_id)

        if not version:
            raise ToolExecutionFailed("wasla", "No version found to submit")

        payload = version.get("payload", {})
        if not payload.get("categories"):
            raise ToolExecutionFailed("wasla", "Cannot submit: store has no categories")

        result = await self._waslak_request(
            ctx, "POST", "/api/agent/v1/stores/drafts", json_body=payload
        )

        waslak_draft_id = result.get("id") or result.get("draftId")

        await store.update_version_status(
            ctx.tenant_id, version["id"],
            status="submitted",
            waslak_draft_id=waslak_draft_id,
            waslak_status="PENDING",
        )
        await store.update_project_status(ctx.tenant_id, project_id, "submitted")

        return {
            "submitted": True,
            "project_id": project_id,
            "version_id": version["id"],
            "waslak_draft_id": waslak_draft_id,
            "waslak_status": "PENDING",
        }

    async def check_submission_status(
        self,
        ctx: ExecutionContext,
        project_id: str,
        version_id: Optional[str] = None,
    ) -> dict[str, Any]:
        from app.services import wasla_project_store as store

        if version_id:
            version = await store.get_version(ctx.tenant_id, version_id)
        else:
            version = await store.get_latest_version(ctx.tenant_id, project_id)

        if not version or not version.get("waslak_draft_id"):
            return {"status": "not_submitted", "project_id": project_id}

        try:
            remote = await self._waslak_request(
                ctx, "GET", f"/api/agent/v1/stores/drafts/{version['waslak_draft_id']}"
            )
        except Exception as e:
            logger.warning("Failed to poll Waslak status: %s", e)
            return {
                "status": version.get("waslak_status", "unknown"),
                "waslak_draft_id": version["waslak_draft_id"],
                "error": str(e),
            }

        new_status = remote.get("status", version.get("waslak_status"))
        merchant_id = remote.get("merchantId")
        rejection_reason = remote.get("rejectionReason")

        await store.update_version_status(
            ctx.tenant_id, version["id"],
            status="approved" if new_status == "APPROVED" else ("rejected" if new_status == "REJECTED" else "submitted"),
            waslak_status=new_status,
            rejection_reason=rejection_reason,
        )

        if new_status == "APPROVED":
            await store.update_project_status(ctx.tenant_id, project_id, "approved")
        elif new_status == "REJECTED":
            await store.update_project_status(ctx.tenant_id, project_id, "rejected")

        return {
            "status": new_status,
            "waslak_draft_id": version["waslak_draft_id"],
            "merchant_id": merchant_id,
            "rejection_reason": rejection_reason,
        }

    # ── Read operations ──────────────────────────────────────────────

    async def get_project_detail(
        self, ctx: ExecutionContext, project_id: str
    ) -> Optional[dict]:
        from app.services import wasla_project_store as store
        return await store.get_project(ctx.tenant_id, project_id)

    async def list_projects(
        self, ctx: ExecutionContext, status: Optional[str] = None, limit: int = 20
    ) -> list[dict]:
        from app.services import wasla_project_store as store
        return await store.list_projects(ctx.tenant_id, status=status, limit=limit)

    async def get_project_versions(
        self, ctx: ExecutionContext, project_id: str
    ) -> list[dict]:
        from app.services import wasla_project_store as store
        return await store.list_versions(ctx.tenant_id, project_id)

    async def get_version_patches(
        self, ctx: ExecutionContext, version_id: str
    ) -> list[dict]:
        from app.services import wasla_project_store as store
        return await store.list_patches(ctx.tenant_id, version_id)

    # ── Merchant operations ──────────────────────────────────────────

    async def list_merchants(
        self, ctx: ExecutionContext, page: int = 1, per_page: int = 20
    ) -> dict[str, Any]:
        merchants = await self._waslak_request(ctx, "GET", "/api/agent/v1/merchants")
        if isinstance(merchants, list):
            return {"merchants": merchants, "count": len(merchants)}
        return merchants

    async def get_merchant_insights(
        self, ctx: ExecutionContext, merchant_id: str
    ) -> dict[str, Any]:
        order_summary = await self._waslak_request(
            ctx, "GET", f"/api/agent/v1/merchants/{merchant_id}/orders"
        )
        from app.agents.waslak_agent import suggest_improvements
        suggestions = await suggest_improvements(order_summary, merchant_id)
        return {
            "merchant_id": merchant_id,
            "order_summary": order_summary,
            "suggestions": suggestions,
        }

    # ── Legacy compatibility ─────────────────────────────────────────

    async def generate_store_draft(
        self, ctx: ExecutionContext, merchant_description: str,
        merchant_name: Optional[str] = None, style_preferences: Optional[dict] = None,
    ) -> dict[str, Any]:
        return await self.create_store_project(
            ctx, merchant_description, merchant_name,
            style_preferences=style_preferences,
        )

    async def submit_draft_to_waslak(
        self, ctx: ExecutionContext, draft_data: dict, merchant_id: Optional[str] = None,
    ) -> dict[str, Any]:
        return await self._waslak_request(
            ctx, "POST", "/api/agent/v1/stores/drafts", json_body=draft_data
        )

    async def get_draft(self, ctx: ExecutionContext, local_id: str) -> dict[str, Any]:
        from app.services import wasla_project_store as store
        project = await store.get_project(ctx.tenant_id, local_id)
        if project:
            version = await store.get_latest_version(ctx.tenant_id, local_id)
            return {**project, "latest_version": version}
        from app.services.waslak_draft_store import get_draft
        legacy = await get_draft(local_id)
        return legacy or {}
