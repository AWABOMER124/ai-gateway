"""
PATCH FILE — historical reference for router wiring. app/main.py is now
tracked directly in the server's git repo (as of 2026-08-03), so it no longer
needs to be hand-patched from this file — just edit app/main.py itself and
commit it normally. Kept only as a quick reminder of the two-step pattern
(import + include_router) for anyone adding a new router.

Note: app/main.py also has a global exception_handler for
app.services.openai_usage.SpendLimitExceeded (returns a clean 429) — added
2026-08-03 alongside the OpenAI daily spend cap. New routers don't need to
touch it; it applies globally.
"""

# ── Add these imports at the top of main.py ──────────────────────────
from app.routers.agent     import router as agent_router
from app.routers.email     import router as email_router
from app.routers.olivery   import router as olivery_router
from app.routers.files     import router as files_router
from app.routers.approvals import router as approvals_router
from app.routers.waslak    import router as waslak_router

# ── Add these include_router calls after existing ones ───────────────
# app.include_router(agent_router)
# app.include_router(email_router)
# app.include_router(olivery_router)
# app.include_router(files_router)
# app.include_router(approvals_router)
# app.include_router(waslak_router)
