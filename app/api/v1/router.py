"""
API v1 Router — versioned multi-tenant endpoints for AI Core.

New products (QIAD, Wasla) use these endpoints with service JWT auth.
Legacy endpoints (app/routers/*) continue to work unchanged.

Security:
- Tenant identity comes from verified JWT claims, NEVER from request body/query
- All endpoints extract ExecutionContext from the JWT
- Cross-tenant access is impossible by construction
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.context import ExecutionContext
from app.core.errors import AICoreError, AuthError
from app.core.security import verify_service_token, build_context_from_token
from app.tools.executor import execute_tool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["v1"])


# ── Auth dependency ────────────────────────────────────────────────


async def _extract_context(authorization: str = Header(...)) -> ExecutionContext:
    """
    Extract and verify ExecutionContext from the Authorization header.

    The JWT is signed by the calling product with a shared secret.
    tenant_id comes from the verified 'org' claim.
    """
    if not authorization.startswith("Bearer "):
        raise AuthError("Authorization header must use Bearer scheme")

    token = authorization[7:]
    claims = verify_service_token(token)
    return build_context_from_token(claims)


# ── Request/Response models ────────────────────────────────────────


class ToolCallRequest(BaseModel):
    tool: str = Field(..., description="Registered tool key")
    params: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class ToolCallResponse(BaseModel):
    status: str
    tool: str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    request_id: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    product: str | None = None
    tenant_id: str | None = None


# ── Endpoints ──────────────────────────────────────────────────────


@router.get("/health")
async def health():
    """Public health check (no auth required)."""
    return HealthResponse(status="ok", version="1.0.0")


@router.post("/tools/call", response_model=ToolCallResponse)
async def call_tool(
    body: ToolCallRequest,
    authorization: str = Header(...),
):
    """
    Execute a registered tool within the caller's tenant context.

    The tool is looked up in the registry, authorized against the
    policy engine, and executed with full audit logging.
    """
    ctx = await _extract_context(authorization)

    try:
        result = await execute_tool(
            ctx=ctx,
            tool_key=body.tool,
            params=body.params,
            idempotency_key=body.idempotency_key,
        )
        return ToolCallResponse(
            status="ok",
            tool=body.tool,
            result=result,
            request_id=ctx.request_id,
        )
    except AICoreError as e:
        return JSONResponse(
            status_code=e.http_status,
            content=e.to_response(),
        )


@router.get("/context")
async def get_context(authorization: str = Header(...)):
    """
    Debug endpoint: return the verified context for this token.
    Useful for integration testing. Disabled in production via feature flag.
    """
    ctx = await _extract_context(authorization)
    return {
        "tenant_id": ctx.tenant_id,
        "product": ctx.product.value,
        "actor": {
            "type": ctx.actor.type.value,
            "id": ctx.actor.id,
            "display_name": ctx.actor.display_name,
        },
        "agent_mode": ctx.agent_mode.value,
        "request_id": ctx.request_id,
        "language": ctx.language,
    }


@router.get("/tools")
async def list_available_tools(authorization: str = Header(...)):
    """List tools available to the caller's product."""
    ctx = await _extract_context(authorization)

    from app.tools.registry import tool_registry
    tools = tool_registry.list_tools(product=ctx.product)

    return {
        "product": ctx.product.value,
        "tools": [
            {
                "key": t.key,
                "description": t.description,
                "risk_level": t.risk_level.value,
                "version": t.version,
            }
            for t in tools
        ],
    }
