"""
Dashboard — small-team web UI: session login, scoped integration API key
management, and the skill readiness page. Server-rendered (Jinja2), no
build step, no JS framework.
"""
import os
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.services import dashboard_users, api_keys, skill_runs, audit_log, openai_usage
from app.services import skill_registry
from app.services.security import hash_password, verify_password, create_session_token, verify_session_token

router = APIRouter(prefix="/dashboard")
templates = Jinja2Templates(directory="app/templates")

COOKIE_NAME = "gw_session"
COOKIE_SECURE = os.getenv("DASHBOARD_COOKIE_SECURE", "true").lower() != "false"

# (scope, label, dangerous?) — dangerous scopes get a visible warning on the create-key form.
SCOPE_CHOICES = [
    ("agent:write", "Agent — إنشاء/مراجعة المهام", False),
    ("email:write", "Email — صياغة الردود", False),
    ("olivery:read", "Olivery — قراءة التقارير", False),
    ("olivery:write", "Olivery — تعديل الطلبات (مسودة فقط)", False),
    ("files:write", "Files — تحليل الملفات", False),
    ("waslak:draft", "Waslak — توليد مسودات متاجر", False),
    ("waslak:read", "Waslak — قراءة التجار/المسودات", False),
    ("waslak:insights", "Waslak — قراءة التحليلات", False),
    ("approvals:read", "Approvals — قراءة الحالة", False),
    ("approvals:decide", "Approvals — تنفيذ الموافقات (⚠️ إجراء حقيقي تلقائي)", True),
]


def _current_user(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return verify_session_token(token)


# ── auth ────────────────────────────────────────────────────────────────

@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    user = await dashboard_users.get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        return templates.TemplateResponse(
            request, "login.html", {"error": "بيانات الدخول غير صحيحة"}
        )
    resp = RedirectResponse("/dashboard", status_code=302)
    token = create_session_token(str(user["id"]), user["role"])
    resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", secure=COOKIE_SECURE, max_age=7 * 24 * 3600)
    await dashboard_users.touch_last_login(user["id"])
    return resp


@router.post("/logout")
async def logout():
    resp = RedirectResponse("/dashboard/login", status_code=302)
    resp.delete_cookie(COOKIE_NAME)
    return resp


# ── overview ────────────────────────────────────────────────────────────

@router.get("")
async def overview(request: Request):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)

    integrations = {
        "OpenAI": bool(os.getenv("OPENAI_API_KEY")),
        "Olivery": bool(os.getenv("OLIVERY_BASE_URL") and os.getenv("OLIVERY_LOGIN") and os.getenv("OLIVERY_PASSWORD")),
        "Waslak": bool(os.getenv("WASLAK_BASE_URL") and os.getenv("WASLAK_API_KEY")),
        "SMTP": bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER")),
    }
    spend_today = await openai_usage.get_spend_today()
    recent_audit = await audit_log.list_recent(20)

    return templates.TemplateResponse(request, "overview.html", {
        "user": user, "active": "overview",
        "integrations": integrations, "spend_today": spend_today,
        "recent_audit": recent_audit,
    })


# ── API keys ────────────────────────────────────────────────────────────

@router.get("/api-keys")
async def api_keys_page(request: Request, error: str | None = None):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)
    keys = await api_keys.list_keys()
    return templates.TemplateResponse(request, "api_keys.html", {
        "user": user, "active": "api-keys", "keys": keys,
        "scope_choices": SCOPE_CHOICES, "new_key": None, "error": error,
    })


@router.post("/api-keys/create")
async def create_api_key(request: Request, name: str = Form(...), scopes: list[str] = Form(default=[])):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)
    if user["role"] != "owner":
        return RedirectResponse("/dashboard/api-keys?error=owner_only", status_code=302)

    full_key, row = await api_keys.issue_key(name, scopes, user["user_id"])
    keys = await api_keys.list_keys()
    return templates.TemplateResponse(request, "api_keys.html", {
        "user": user, "active": "api-keys", "keys": keys,
        "scope_choices": SCOPE_CHOICES, "new_key": full_key, "error": None,
    })


@router.post("/api-keys/{key_id}/revoke")
async def revoke_api_key(request: Request, key_id: str):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)
    if user["role"] != "owner":
        return RedirectResponse("/dashboard/api-keys?error=owner_only", status_code=302)
    await api_keys.revoke_key(key_id)
    return RedirectResponse("/dashboard/api-keys", status_code=302)


# ── skill readiness ─────────────────────────────────────────────────────

@router.get("/skills")
async def skills_page(request: Request):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)

    latest = await skill_runs.get_latest_per_skill()
    latest_by_key = {(r["skill_code"], r["check_type"]): r for r in latest}
    recent = await skill_runs.list_recent(limit=15)

    skills_view = []
    for code, meta in skill_registry.SKILLS.items():
        skills_view.append({
            "code": code, "label": meta["label"],
            "health": latest_by_key.get((code, "health")),
            "capability": latest_by_key.get((code, "capability")),
        })

    return templates.TemplateResponse(request, "skills.html", {
        "user": user, "active": "skills",
        "skills": skills_view, "recent": recent,
    })


@router.post("/skills/{code}/health")
async def run_health(request: Request, code: str):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)
    meta = skill_registry.SKILLS.get(code)
    if meta:
        result = await meta["health_check"]()
        await skill_runs.record_run(
            skill_code=code, check_type="health", passed=result["passed"], score=None,
            summary=result["summary"], output_excerpt="", triggered_by=user["user_id"],
        )
    return RedirectResponse("/dashboard/skills", status_code=302)


@router.post("/skills/{code}/capability")
async def run_capability(request: Request, code: str):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/dashboard/login", status_code=302)
    meta = skill_registry.SKILLS.get(code)
    if meta:
        result = await meta["capability_test"]()
        await skill_runs.record_run(
            skill_code=code, check_type="capability", passed=result["passed"], score=result.get("score"),
            summary=result["summary"], output_excerpt=result.get("output_excerpt", ""), triggered_by=user["user_id"],
        )
    return RedirectResponse("/dashboard/skills", status_code=302)
