"""
Wasla API v1 endpoints — multi-tenant Store Project V2.

Called by Wasla platform with service JWT auth.
Provides store project lifecycle: create → edit → submit → track.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx
from fastapi import APIRouter, File, Form, Header, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.v1.router import _extract_context
from app.core.context import ExecutionContext
from app.core.errors import AICoreError, ToolExecutionFailed, ToolPermissionDenied, ValidationError
from app.integrations.wasla.adapter import WaslaAdapter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/wasla", tags=["v1-wasla"])

_adapter = WaslaAdapter()


def _require_permission(ctx: ExecutionContext, permission: str) -> None:
    """Enforce the permission carried by the verified Wasla service JWT."""
    permissions = set(ctx.actor.permissions)
    if "*" not in permissions and permission not in permissions:
        raise ToolPermissionDenied(
            permission,
            message=f"Permission denied: {permission}",
            request_id=ctx.request_id,
        )


def _error_response(error: AICoreError) -> JSONResponse:
    return JSONResponse(status_code=error.http_status, content=error.to_response())


class CreateProjectRequest(BaseModel):
    merchant_description: str = Field(..., max_length=2000)
    merchant_name: Optional[str] = Field(None, max_length=120)
    business_type: Optional[str] = Field(None, description="ecommerce, restaurant, landing_page")
    style_preferences: Optional[dict] = None


class RegenerateRequest(BaseModel):
    prompt: Optional[str] = Field(None, max_length=2000)
    style_preferences: Optional[dict] = None


class PatchRequest(BaseModel):
    patch_type: str = Field(..., description="add_category, remove_category, edit_product, edit_style, edit_info, ai_refine")
    patch_data: dict[str, Any] = Field(default_factory=dict)


class RestoreVersionRequest(BaseModel):
    version_id: str = Field(..., min_length=1, max_length=100)


class MerchantCopilotRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)
    snapshot: dict[str, Any]
    language: str = Field("ar", pattern="^(ar|en)$")


class SubmitRequest(BaseModel):
    version_id: Optional[str] = None


IMAGE_MODES = {"TRANSPARENT", "CLEAN_WHITE", "LIFESTYLE"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _product_image_prompt(mode: str, scene: str) -> str:
    immutable = "Preserve the exact product identity, shape, proportions, colors, materials, labels, logos, packaging, and all readable text. Do not invent, remove, distort, recolor, or redesign any product detail."
    if mode == "TRANSPARENT":
        return f"{immutable} Precisely isolate the product, remove only its existing background, refine edges and natural contact shadows, and return a transparent background. Center the complete product with comfortable margins."
    if mode == "CLEAN_WHITE":
        return f"{immutable} Create a premium ecommerce studio photo on a seamless pure white background. Improve exposure, sharpness, color balance, edge quality, and add only a subtle realistic contact shadow. No props, text, watermark, border, or gradient."
    return f"{immutable} Place the unchanged product in {scene or 'a tasteful premium environment appropriate for this product and its customer'}. Produce a photorealistic commercial product photograph with coherent scale, lighting, and natural shadows. No text, badges, watermarks, hands, people, or competing products."


async def _enhance_product_image(image: bytes, mode: str, scene: str) -> dict[str, str]:
    from app.config import settings
    if not settings.openai_api_key:
        raise ToolExecutionFailed("images.enhance", "Image provider is not configured")
    transparent = mode == "TRANSPARENT"
    model = __import__('os').getenv("AI_IMAGE_MODEL", "gpt-image-2")
    form = {
        "model": (None, model),
        "prompt": (None, _product_image_prompt(mode, scene)),
        "size": (None, "1024x1024"),
        "quality": (None, "medium"),
        "background": (None, "transparent" if transparent else "opaque"),
        "output_format": (None, "png" if transparent else "webp"),
        "image[]": ("product.webp", image, "image/webp"),
    }
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post("https://api.openai.com/v1/images/edits", headers={"Authorization": f"Bearer {settings.openai_api_key}"}, files=form)
    if not response.is_success:
        logger.warning("Image provider rejected request: %s", response.status_code)
        raise ToolExecutionFailed("images.enhance", "Image enhancement provider failed")
    encoded = (response.json().get("data") or [{}])[0].get("b64_json")
    if not encoded:
        raise ToolExecutionFailed("images.enhance", "Image enhancement returned no image")
    return {"image_base64": encoded, "mime_type": "image/png" if transparent else "image/webp", "filename": "product-transparent.png" if transparent else "product-enhanced.webp", "model": model}


@router.post("/projects")
async def create_project(
    body: CreateProjectRequest,
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
    try:
        _require_permission(ctx, "store.generate")
        result = await _adapter.create_store_project(
            ctx,
            merchant_description=body.merchant_description,
            merchant_name=body.merchant_name,
            business_type=body.business_type,
            style_preferences=body.style_preferences,
        )
        return {"status": "ok", "request_id": ctx.request_id, **result}
    except AICoreError as e:
        return _error_response(e)


@router.get("/projects")
async def list_projects(
    authorization: str = Header(...),
    status: Optional[str] = Query(None),
    limit: int = Query(20, le=50),
):
    ctx = await _extract_context(authorization)
    try:
        _require_permission(ctx, "store.view")
        projects = await _adapter.list_projects(ctx, status=status, limit=limit)
        return {
            "count": len(projects),
            "projects": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "business_type": p.get("business_type"),
                    "status": p["status"],
                    "current_version": p["current_version"],
                    "created_at": str(p["created_at"]),
                    "updated_at": str(p["updated_at"]),
                }
                for p in projects
            ],
        }
    except AICoreError as e:
        return _error_response(e)


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
    try:
        _require_permission(ctx, "store.view")
        project = await _adapter.get_project_detail(ctx, project_id)
        if not project:
            return JSONResponse(status_code=404, content={"error": {"code": "RESOURCE_NOT_FOUND", "message": f"Project not found: {project_id}"}})

        from app.services import wasla_project_store as store
        latest = await store.get_latest_version(ctx.tenant_id, project_id)

        return {
            "project": {
                "id": project["id"],
                "name": project["name"],
                "description": project.get("description"),
                "business_type": project.get("business_type"),
                "style": project.get("style", {}),
                "status": project["status"],
                "current_version": project["current_version"],
                "created_at": str(project["created_at"]),
            },
            "latest_version": {
                "id": latest["id"],
                "version_number": latest["version_number"],
                "payload": latest.get("payload", {}),
                "validation_errors": latest.get("validation_errors", []),
                "status": latest["status"],
                "waslak_draft_id": latest.get("waslak_draft_id"),
                "waslak_status": latest.get("waslak_status"),
                "created_at": str(latest["created_at"]),
            } if latest else None,
        }
    except AICoreError as e:
        return _error_response(e)


@router.get("/projects/{project_id}/versions")
async def list_versions(
    project_id: str,
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
    try:
        _require_permission(ctx, "store.view")
        versions = await _adapter.get_project_versions(ctx, project_id)
        return {
            "project_id": project_id,
            "count": len(versions),
            "versions": [
                {
                    "id": v["id"],
                    "version_number": v["version_number"],
                    "status": v["status"],
                    "waslak_status": v.get("waslak_status"),
                    "created_at": str(v["created_at"]),
                }
                for v in versions
            ],
        }
    except AICoreError as e:
        return _error_response(e)


@router.post("/projects/{project_id}/regenerate")
async def regenerate_version(
    project_id: str,
    body: RegenerateRequest,
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
    try:
        _require_permission(ctx, "store.generate")
        result = await _adapter.regenerate_version(
            ctx, project_id,
            prompt=body.prompt,
            style_preferences=body.style_preferences,
        )
        return {"status": "ok", "request_id": ctx.request_id, **result}
    except AICoreError as e:
        return _error_response(e)


@router.post("/projects/{project_id}/patch")
async def apply_patch(
    project_id: str,
    body: PatchRequest,
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
    try:
        _require_permission(ctx, "store.generate")
        result = await _adapter.apply_patch(
            ctx, project_id,
            patch_type=body.patch_type,
            patch_data=body.patch_data,
        )
        return {"status": "ok", "request_id": ctx.request_id, **result}
    except AICoreError as e:
        return _error_response(e)


@router.post("/projects/{project_id}/restore")
async def restore_version(
    project_id: str,
    body: RestoreVersionRequest,
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
    try:
        _require_permission(ctx, "store.generate")
        result = await _adapter.restore_version(ctx, project_id, body.version_id)
        return {"status": "ok", "request_id": ctx.request_id, **result}
    except AICoreError as e:
        return _error_response(e)


@router.post("/projects/{project_id}/submit")
async def submit_project(
    project_id: str,
    body: SubmitRequest,
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
    try:
        _require_permission(ctx, "store.submit")
        result = await _adapter.submit_to_waslak(
            ctx, project_id, version_id=body.version_id,
        )
        return {"status": "ok", "request_id": ctx.request_id, **result}
    except AICoreError as e:
        return _error_response(e)


@router.get("/projects/{project_id}/status")
async def check_status(
    project_id: str,
    authorization: str = Header(...),
    version_id: Optional[str] = Query(None),
):
    ctx = await _extract_context(authorization)
    try:
        _require_permission(ctx, "store.view")
        result = await _adapter.check_submission_status(
            ctx, project_id, version_id=version_id,
        )
        return {"request_id": ctx.request_id, **result}
    except AICoreError as e:
        return _error_response(e)


@router.get("/merchants")
async def list_merchants(
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
    try:
        _require_permission(ctx, "merchants.view")
        result = await _adapter.list_merchants(ctx)
        return {"request_id": ctx.request_id, **result}
    except AICoreError as e:
        return _error_response(e)


@router.post("/copilot")
async def merchant_copilot(
    body: MerchantCopilotRequest,
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
    try:
        _require_permission(ctx, "merchants.view")
        if len(json.dumps(body.snapshot, ensure_ascii=False)) > 100_000:
            return JSONResponse(status_code=413, content={"error": {"code": "PAYLOAD_TOO_LARGE", "message": "Snapshot is too large"}})
        from app.agents.waslak_agent import answer_merchant_question
        answer = await answer_merchant_question(body.question, body.snapshot, body.language)
        return {"status": "ok", "request_id": ctx.request_id, "answer": answer}
    except AICoreError as e:
        return _error_response(e)


@router.post("/images/enhance")
async def enhance_product_image(
    image: UploadFile = File(...),
    mode: str = Form(...),
    scene: str = Form(""),
    authorization: str = Header(...),
):
    """Enhance a product image through AI Core; provider credentials never leave AI Core."""
    ctx = await _extract_context(authorization)
    try:
        _require_permission(ctx, "images.enhance")
        if mode not in IMAGE_MODES:
            raise ValidationError("Unsupported image enhancement mode")
        if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise ValidationError("Only JPEG, PNG, and WebP product images are accepted")
        source = await image.read(MAX_IMAGE_BYTES + 1)
        if not source or len(source) > MAX_IMAGE_BYTES:
            raise ValidationError("Product image must be between 1 byte and 8 MB")
        result = await _enhance_product_image(source, mode, scene[:500])
        return {"status": "ok", "request_id": ctx.request_id, **result}
    except AICoreError as e:
        return _error_response(e)


@router.get("/merchants/{merchant_id}/insights")
async def merchant_insights(
    merchant_id: str,
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
    try:
        _require_permission(ctx, "merchants.view")
        result = await _adapter.get_merchant_insights(ctx, merchant_id)
        return {"request_id": ctx.request_id, **result}
    except AICoreError as e:
        return _error_response(e)
