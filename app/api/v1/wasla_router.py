"""
Wasla API v1 endpoints — multi-tenant Store Project V2.

Called by Wasla platform with service JWT auth.
Provides store project lifecycle: create → edit → submit → track.
"""
from __future__ import annotations

import logging
import json
from typing import Any, Optional

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.v1.router import _extract_context
from app.core.errors import AICoreError
from app.integrations.wasla.adapter import WaslaAdapter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/wasla", tags=["v1-wasla"])

_adapter = WaslaAdapter()


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


@router.post("/projects")
async def create_project(
    body: CreateProjectRequest,
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
    try:
        result = await _adapter.create_store_project(
            ctx,
            merchant_description=body.merchant_description,
            merchant_name=body.merchant_name,
            business_type=body.business_type,
            style_preferences=body.style_preferences,
        )
        return {"status": "ok", "request_id": ctx.request_id, **result}
    except AICoreError as e:
        return JSONResponse(status_code=e.http_status, content=e.to_response())


@router.get("/projects")
async def list_projects(
    authorization: str = Header(...),
    status: Optional[str] = Query(None),
    limit: int = Query(20, le=50),
):
    ctx = await _extract_context(authorization)
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


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
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


@router.get("/projects/{project_id}/versions")
async def list_versions(
    project_id: str,
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
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


@router.post("/projects/{project_id}/regenerate")
async def regenerate_version(
    project_id: str,
    body: RegenerateRequest,
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
    try:
        result = await _adapter.regenerate_version(
            ctx, project_id,
            prompt=body.prompt,
            style_preferences=body.style_preferences,
        )
        return {"status": "ok", "request_id": ctx.request_id, **result}
    except AICoreError as e:
        return JSONResponse(status_code=e.http_status, content=e.to_response())


@router.post("/projects/{project_id}/patch")
async def apply_patch(
    project_id: str,
    body: PatchRequest,
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
    try:
        result = await _adapter.apply_patch(
            ctx, project_id,
            patch_type=body.patch_type,
            patch_data=body.patch_data,
        )
        return {"status": "ok", "request_id": ctx.request_id, **result}
    except AICoreError as e:
        return JSONResponse(status_code=e.http_status, content=e.to_response())


@router.post("/projects/{project_id}/restore")
async def restore_version(
    project_id: str,
    body: RestoreVersionRequest,
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
    try:
        result = await _adapter.restore_version(ctx, project_id, body.version_id)
        return {"status": "ok", "request_id": ctx.request_id, **result}
    except AICoreError as e:
        return JSONResponse(status_code=e.http_status, content=e.to_response())


@router.post("/projects/{project_id}/submit")
async def submit_project(
    project_id: str,
    body: SubmitRequest,
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
    try:
        result = await _adapter.submit_to_waslak(
            ctx, project_id, version_id=body.version_id,
        )
        return {"status": "ok", "request_id": ctx.request_id, **result}
    except AICoreError as e:
        return JSONResponse(status_code=e.http_status, content=e.to_response())


@router.get("/projects/{project_id}/status")
async def check_status(
    project_id: str,
    authorization: str = Header(...),
    version_id: Optional[str] = Query(None),
):
    ctx = await _extract_context(authorization)
    try:
        result = await _adapter.check_submission_status(
            ctx, project_id, version_id=version_id,
        )
        return {"request_id": ctx.request_id, **result}
    except AICoreError as e:
        return JSONResponse(status_code=e.http_status, content=e.to_response())


@router.get("/merchants")
async def list_merchants(
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
    try:
        result = await _adapter.list_merchants(ctx)
        return {"request_id": ctx.request_id, **result}
    except AICoreError as e:
        return JSONResponse(status_code=e.http_status, content=e.to_response())


@router.post("/copilot")
async def merchant_copilot(
    body: MerchantCopilotRequest,
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
    if len(json.dumps(body.snapshot, ensure_ascii=False)) > 100_000:
        return JSONResponse(status_code=413, content={"error": {"code": "PAYLOAD_TOO_LARGE", "message": "Snapshot is too large"}})
    try:
        from app.agents.waslak_agent import answer_merchant_question
        answer = await answer_merchant_question(body.question, body.snapshot, body.language)
        return {"status": "ok", "request_id": ctx.request_id, "answer": answer}
    except AICoreError as e:
        return JSONResponse(status_code=e.http_status, content=e.to_response())


@router.get("/merchants/{merchant_id}/insights")
async def merchant_insights(
    merchant_id: str,
    authorization: str = Header(...),
):
    ctx = await _extract_context(authorization)
    try:
        result = await _adapter.get_merchant_insights(ctx, merchant_id)
        return {"request_id": ctx.request_id, **result}
    except AICoreError as e:
        return JSONResponse(status_code=e.http_status, content=e.to_response())
