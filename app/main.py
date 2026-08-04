"""
main.py — FastAPI application entry point.
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


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s — %(message)s',
    datefmt='%H:%M:%S',
)

app = FastAPI(
    title='Awab AI Operator — API Gateway',
    description='API يستقبل أسئلة ويرجع إجابات بأسلوب أواب من قاعدة المعرفة.',
    version='0.1.0',
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
