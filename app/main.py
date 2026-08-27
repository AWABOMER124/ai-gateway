"""
main.py — FastAPI application entry point.

Unified Multi-Tenant AI Core platform.
Legacy endpoints (/agent/*, /waslak/*, /email/*, etc.) are preserved.
New multi-tenant endpoints live under /api/v1/.
"""

import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import health, ask, search
from app.routers import agent as agent_r, email as email_r, olivery as olivery_r, files as files_r, approvals as approvals_r
from app.routers import waslak as waslak_r
from app.routers import dashboard as dashboard_r
from app.services.openai_usage import SpendLimitExceeded
from app.core.errors import AICoreError
from app.api.v1.router import router as v1_router
from app.api.v1.qiad_router import router as v1_qiad_router
from app.api.v1.wasla_router import router as v1_wasla_router


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s — %(message)s',
    datefmt='%H:%M:%S',
)

app = FastAPI(
    title='AI Core — Unified Intelligence Platform',
    description='Multi-tenant AI platform powering QIAD, Wasla, and legacy services.',
    version='1.0.0',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(health.router, tags=['System'])
app.include_router(ask.router,    tags=['Ask'])
app.include_router(search.router, tags=['Search'])


@app.get('/', include_in_schema=False)
def root():
    return {'message': 'Awab AI Operator API — اذهب إلى /docs'}


@app.exception_handler(SpendLimitExceeded)
async def spend_limit_handler(request: Request, exc: SpendLimitExceeded):
    return JSONResponse(status_code=429, content={'detail': str(exc)})

app.include_router(agent_r.router, tags=['Agent'])
app.include_router(email_r.router, tags=['Email'])
app.include_router(olivery_r.router, tags=['Olivery'])
app.include_router(files_r.router, tags=['Files'])
app.include_router(approvals_r.router, tags=['Approvals'])
app.include_router(waslak_r.router, tags=['Waslak'])
app.include_router(dashboard_r.router, tags=['Dashboard'], include_in_schema=False)

# ── v1 Multi-tenant API ──
app.include_router(v1_router, tags=['v1'])
app.include_router(v1_qiad_router, tags=['v1-qiad'])
app.include_router(v1_wasla_router, tags=['v1-wasla'])


# ── AICoreError handler (multi-tenant error format) ──
@app.exception_handler(AICoreError)
async def ai_core_error_handler(request: Request, exc: AICoreError):
    return JSONResponse(status_code=exc.http_status, content=exc.to_response())


# ── Startup: bootstrap legacy tenant ──
@app.on_event("startup")
async def _bootstrap():
    """Ensure the legacy tenant exists so existing endpoints keep working."""
    try:
        from app.core.tenancy import bootstrap_legacy_tenant_sync
        import asyncio
        await asyncio.to_thread(bootstrap_legacy_tenant_sync)
        logging.getLogger(__name__).info("Legacy tenant bootstrapped")
    except Exception as e:
        # Don't crash the app if migration hasn't run yet
        logging.getLogger(__name__).warning("Legacy tenant bootstrap skipped: %s", e)
