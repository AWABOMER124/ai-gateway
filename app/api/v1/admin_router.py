"""
Admin API — health checks, config management, token generation.

Served at /api/v1/admin. The HTML dashboard is embedded and served
at GET /api/v1/admin/ so no template files are needed.

Protected by AI_CORE_SERVICE_SECRET header check.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Header, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["v1-admin"])


def _check_admin_auth(authorization: str):
    secret = os.getenv("AI_CORE_SERVICE_SECRET", "")
    if not secret:
        return
    token = authorization.replace("Bearer ", "").strip() if authorization else ""
    if token != secret:
        from app.core.errors import AuthError
        raise AuthError("Invalid admin token")


# ── Health ──────────────────────────────────────────────────────────


@router.get("/health")
async def full_health_check(authorization: str = Header("")):
    _check_admin_auth(authorization)

    checks = {}

    checks["database"] = await _check_db()
    checks["openai"] = _check_env("OPENAI_API_KEY")
    checks["waslak"] = _check_env("WASLAK_BASE_URL", "WASLAK_API_KEY")
    checks["jwt_wasla"] = _check_env("AI_CORE_SECRET_WASLA")
    checks["jwt_qiad"] = _check_env("AI_CORE_SECRET_QIAD")
    checks["qiad_api"] = _check_env("QIAD_API_URL", "QIAD_SERVICE_TOKEN")

    all_ok = all(c["status"] == "ok" for c in checks.values())

    return {
        "overall": "healthy" if all_ok else "degraded",
        "checks": checks,
        "timestamp": int(time.time()),
    }


async def _check_db() -> dict:
    try:
        from app.services.db_pool import pooled_cursor

        def _ping():
            with pooled_cursor(commit=False) as cur:
                cur.execute("SELECT 1")
                return True
        await asyncio.to_thread(_ping)
        return {"status": "ok", "message": "متصل"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:120]}


def _check_env(*keys: str) -> dict:
    missing = [k for k in keys if not os.getenv(k)]
    if not missing:
        return {"status": "ok", "message": "مُعد"}
    return {"status": "missing", "message": f"مفقود: {', '.join(missing)}"}


# ── Config Status ───────────────────────────────────────────────────


@router.get("/config")
async def config_status(authorization: str = Header("")):
    _check_admin_auth(authorization)

    env_vars = [
        ("DATABASE_URL", "قاعدة البيانات"),
        ("OPENAI_API_KEY", "OpenAI"),
        ("CHAT_MODEL", "نموذج الدردشة"),
        ("EMBEDDING_MODEL", "نموذج الـ Embeddings"),
        ("WASLAK_BASE_URL", "Waslak URL"),
        ("WASLAK_API_KEY", "Waslak API Key"),
        ("AI_CORE_SECRET_WASLA", "JWT Secret — وصلة"),
        ("AI_CORE_SECRET_QIAD", "JWT Secret — قياد"),
        ("AI_CORE_SERVICE_SECRET", "Admin Secret"),
        ("QIAD_API_URL", "QIAD API URL"),
        ("QIAD_SERVICE_TOKEN", "QIAD Service Token"),
    ]

    items = []
    for key, label in env_vars:
        val = os.getenv(key, "")
        if val:
            if "key" in key.lower() or "secret" in key.lower() or "token" in key.lower() or "password" in key.lower():
                display = val[:4] + "••••••••" + val[-4:] if len(val) > 8 else "•" * len(val)
            else:
                display = val
            items.append({"key": key, "label": label, "set": True, "value": display})
        else:
            items.append({"key": key, "label": label, "set": False, "value": ""})

    return {"config": items}


# ── Tenant Config ───────────────────────────────────────────────────


class TenantConfigRequest(BaseModel):
    tenant_id: str = Field(..., max_length=100)
    waslak_base_url: str = Field(..., max_length=500)
    waslak_api_key: str = Field(..., max_length=500)
    max_drafts_per_hour: int = Field(30, ge=1, le=200)
    enabled: bool = True


@router.get("/tenant-config")
async def list_tenant_configs(authorization: str = Header("")):
    _check_admin_auth(authorization)

    def _fetch():
        from app.services.db_pool import pooled_cursor
        try:
            with pooled_cursor(commit=False) as cur:
                cur.execute(
                    "SELECT tenant_id, waslak_base_url, enabled, max_drafts_per_hour, created_at, updated_at "
                    "FROM wasla_tenant_config ORDER BY created_at DESC"
                )
                return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []

    rows = await asyncio.to_thread(_fetch)
    for r in rows:
        for k in ("created_at", "updated_at"):
            if r.get(k):
                r[k] = str(r[k])
    return {"tenants": rows}


@router.post("/tenant-config")
async def upsert_tenant_config(body: TenantConfigRequest, authorization: str = Header("")):
    _check_admin_auth(authorization)

    def _upsert():
        from app.services.db_pool import pooled_cursor
        with pooled_cursor() as cur:
            cur.execute(
                """
                INSERT INTO wasla_tenant_config
                    (id, tenant_id, waslak_base_url, waslak_api_key_encrypted, max_drafts_per_hour, enabled)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id) DO UPDATE SET
                    waslak_base_url = EXCLUDED.waslak_base_url,
                    waslak_api_key_encrypted = EXCLUDED.waslak_api_key_encrypted,
                    max_drafts_per_hour = EXCLUDED.max_drafts_per_hour,
                    enabled = EXCLUDED.enabled,
                    updated_at = now()
                """,
                (
                    str(uuid.uuid4()), body.tenant_id, body.waslak_base_url,
                    body.waslak_api_key, body.max_drafts_per_hour, body.enabled,
                ),
            )

    await asyncio.to_thread(_upsert)
    return {"status": "ok", "tenant_id": body.tenant_id}


# ── Token Generation ────────────────────────────────────────────────


class GenerateTokenRequest(BaseModel):
    issuer: str = Field(..., description="wasla or qiad")
    subject: str = Field("test-user", max_length=120)
    organization_id: str = Field("test-org", max_length=120)
    permissions: list[str] = Field(
        default_factory=lambda: ["store.generate", "store.submit", "store.view", "merchants.view"]
    )
    ttl_seconds: int = Field(3600, ge=60, le=86400)


@router.post("/generate-token")
async def generate_token(body: GenerateTokenRequest, authorization: str = Header("")):
    _check_admin_auth(authorization)

    from app.core.security import create_service_token
    try:
        token = create_service_token(
            issuer=body.issuer,
            subject=body.subject,
            organization_id=body.organization_id,
            permissions=body.permissions,
            ttl_seconds=body.ttl_seconds,
        )
        return {
            "token": token,
            "issuer": body.issuer,
            "expires_in": body.ttl_seconds,
            "usage": f"Authorization: Bearer {token}",
        }
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


# ── Migration Status ────────────────────────────────────────────────


@router.get("/migrations")
async def migration_status(authorization: str = Header("")):
    _check_admin_auth(authorization)

    tables_to_check = [
        ("ai_tenants", "010_multi_tenant.sql"),
        ("ai_tenant_products", "010_multi_tenant.sql"),
        ("ai_conversation_memory", "011_conversation_memory.sql"),
        ("wasla_store_projects", "012_wasla_store_projects.sql"),
        ("wasla_store_versions", "012_wasla_store_projects.sql"),
        ("wasla_store_patches", "012_wasla_store_projects.sql"),
        ("wasla_tenant_config", "012_wasla_store_projects.sql"),
    ]

    def _check():
        from app.services.db_pool import pooled_cursor
        results = []
        with pooled_cursor(commit=False) as cur:
            for table, migration in tables_to_check:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    row = cur.fetchone()
                    count = row[0] if row else 0
                    results.append({"table": table, "migration": migration, "exists": True, "rows": count})
                except Exception:
                    results.append({"table": table, "migration": migration, "exists": False, "rows": 0})
                    cur.execute("ROLLBACK")
        return results

    try:
        checks = await asyncio.to_thread(_check)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"DB error: {e}"})

    return {"tables": checks}


# ── Waslak Connection Test ──────────────────────────────────────────


@router.post("/test-waslak")
async def test_waslak_connection(authorization: str = Header("")):
    _check_admin_auth(authorization)

    base_url = os.getenv("WASLAK_BASE_URL", "")
    api_key = os.getenv("WASLAK_API_KEY", "")

    if not base_url or not api_key:
        return {"status": "not_configured", "message": "WASLAK_BASE_URL أو WASLAK_API_KEY مفقود"}

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{base_url.rstrip('/')}/api/agent/v1/merchants",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
        return {
            "status": "ok" if r.status_code < 400 else "error",
            "http_status": r.status_code,
            "message": "متصل بنجاح" if r.status_code < 400 else f"خطأ: {r.status_code}",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


# ── Dashboard HTML ──────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def admin_dashboard():
    return _DASHBOARD_HTML


_DASHBOARD_HTML = """\
<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Core — لوحة التحكم</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {
  --ground:#f4f5f2;--surface:#fff;--surface-dim:#edeee9;
  --ink:#171b22;--ink2:#4a4f5c;--ink3:#7c8190;
  --border:#dfe2db;--accent:#2e5266;--accent-soft:#e4ecef;
  --ok:#2f7a5c;--ok-bg:#dcebe3;--warn:#9c6b0b;--warn-bg:#f1e6cc;
  --err:#a43229;--err-bg:#f3dbd7;
  --font:'IBM Plex Sans Arabic','Segoe UI',system-ui,sans-serif;
  --mono:'IBM Plex Mono','Consolas',monospace;
}
@media(prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#0e1420;--surface:#171e2e;--surface-dim:#1e2738;
    --ink:#e8e6e1;--ink2:#a0a4b0;--ink3:#6b7080;
    --border:#2a3345;--accent:#6b9aff;--accent-soft:rgba(107,154,255,.12);
    --ok:#2dd4a0;--ok-bg:rgba(45,212,160,.1);
    --warn:#f5b731;--warn-bg:rgba(245,183,49,.1);
    --err:#f07070;--err-bg:rgba(240,112,112,.1);
  }
}
:root[data-theme="dark"]{
  --ground:#0e1420;--surface:#171e2e;--surface-dim:#1e2738;
  --ink:#e8e6e1;--ink2:#a0a4b0;--ink3:#6b7080;
  --border:#2a3345;--accent:#6b9aff;--accent-soft:rgba(107,154,255,.12);
  --ok:#2dd4a0;--ok-bg:rgba(45,212,160,.1);
  --warn:#f5b731;--warn-bg:rgba(245,183,49,.1);
  --err:#f07070;--err-bg:rgba(240,112,112,.1);
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:var(--font);background:var(--ground);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:880px;margin:0 auto;padding:2rem 1.5rem 4rem}
h1{font-size:1.5rem;font-weight:700;margin-bottom:.25rem}
.sub{color:var(--ink2);font-size:.88rem;margin-bottom:2rem}
.tabs{display:flex;gap:0;border-bottom:2px solid var(--border);margin-bottom:1.5rem;overflow-x:auto}
.tab{padding:.6rem 1.2rem;font-size:.85rem;font-weight:500;color:var(--ink3);cursor:pointer;border:none;background:none;border-bottom:2px solid transparent;margin-bottom:-2px;font-family:var(--font);white-space:nowrap}
.tab.active{color:var(--accent);border-bottom-color:var(--accent);font-weight:600}
.panel{display:none}.panel.active{display:block}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.25rem;margin-bottom:1rem;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.card h2{font-size:1rem;font-weight:600;margin-bottom:.75rem}
.row{display:flex;align-items:center;gap:.75rem;padding:.5rem 0;border-bottom:1px solid var(--border);flex-wrap:wrap}
.row:last-child{border-bottom:none}
.row-label{font-size:.82rem;color:var(--ink2);min-width:140px;font-weight:500}
.row-value{font-size:.82rem;color:var(--ink);flex:1;font-family:var(--mono);direction:ltr;text-align:left;word-break:break-all}
.pill{display:inline-block;font-size:.7rem;font-weight:600;padding:.15rem .55rem;border-radius:20px}
.pill-ok{background:var(--ok-bg);color:var(--ok)}
.pill-warn{background:var(--warn-bg);color:var(--warn)}
.pill-err{background:var(--err-bg);color:var(--err)}
.form-group{margin-bottom:.85rem}
.form-group label{display:block;font-size:.78rem;color:var(--ink2);margin-bottom:.3rem;font-weight:500}
.form-group input,.form-group select{width:100%;padding:.55rem .75rem;border:1px solid var(--border);border-radius:6px;font-size:.85rem;background:var(--surface);color:var(--ink);font-family:var(--font)}
.form-group input:focus,.form-group select:focus{outline:none;border-color:var(--accent)}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:.75rem}
.btn{background:var(--accent);color:#fff;border:none;border-radius:6px;padding:.55rem 1.2rem;font-size:.82rem;cursor:pointer;font-family:var(--font);font-weight:500}
.btn:hover{opacity:.9}.btn:disabled{opacity:.5;cursor:not-allowed}
.btn-outline{background:transparent;color:var(--accent);border:1px solid var(--accent)}
.result{background:var(--surface-dim);border:1px solid var(--border);border-radius:8px;padding:1rem;margin-top:.75rem;font-family:var(--mono);font-size:.78rem;direction:ltr;text-align:left;word-break:break-all;max-height:200px;overflow-y:auto;white-space:pre-wrap}
.spinner{display:inline-block;width:14px;height:14px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .6s linear infinite;margin-left:.4rem;vertical-align:middle}
@keyframes spin{to{transform:rotate(360deg)}}
.empty{color:var(--ink3);font-size:.85rem;text-align:center;padding:2rem}
@media(max-width:640px){.form-row{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
  <h1>AI Core — لوحة التحكم</h1>
  <p class="sub">إدارة الاتصالات والمفاتيح والإعدادات</p>

  <div class="tabs">
    <button class="tab active" onclick="showTab('health',this)">صحة النظام</button>
    <button class="tab" onclick="showTab('config',this)">الإعدادات</button>
    <button class="tab" onclick="showTab('tenants',this)">المستأجرين</button>
    <button class="tab" onclick="showTab('tokens',this)">توليد توكن</button>
    <button class="tab" onclick="showTab('migrations',this)">Migrations</button>
  </div>

  <div id="panel-health" class="panel active">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.75rem">
        <h2>حالة الخدمات</h2>
        <button class="btn btn-outline" onclick="loadHealth()">تحديث</button>
      </div>
      <div id="health-body"><div class="empty">اضغط تحديث لفحص الاتصالات</div></div>
    </div>
    <div class="card">
      <h2>اختبار اتصال وصلة</h2>
      <p style="font-size:.82rem;color:var(--ink2);margin-bottom:.75rem">يتصل بـ Waslak API ويتحقق من صلاحية المفتاح</p>
      <button class="btn" onclick="testWaslak()" id="btn-waslak">اختبار الاتصال</button>
      <div id="waslak-result"></div>
    </div>
  </div>

  <div id="panel-config" class="panel">
    <div class="card">
      <h2>متغيرات البيئة</h2>
      <div id="config-body"><div class="empty">جارٍ التحميل...</div></div>
    </div>
  </div>

  <div id="panel-tenants" class="panel">
    <div class="card">
      <h2>إعداد مستأجر جديد</h2>
      <div class="form-row">
        <div class="form-group"><label>معرف المستأجر</label><input id="tc-tid" placeholder="wasla-prod"></div>
        <div class="form-group"><label>Waslak Base URL</label><input id="tc-url" dir="ltr" placeholder="https://api.waslak.com"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>Waslak API Key</label><input id="tc-key" type="password" dir="ltr"></div>
        <div class="form-group"><label>الحد الأقصى للمسودات / ساعة</label><input id="tc-limit" type="number" value="30"></div>
      </div>
      <button class="btn" onclick="saveTenant()">حفظ المستأجر</button>
      <div id="tenant-save-result"></div>
    </div>
    <div class="card">
      <h2>المستأجرين المسجلين</h2>
      <div id="tenants-list"><div class="empty">جارٍ التحميل...</div></div>
    </div>
  </div>

  <div id="panel-tokens" class="panel">
    <div class="card">
      <h2>توليد Service JWT</h2>
      <p style="font-size:.82rem;color:var(--ink2);margin-bottom:.75rem">توكن لمنصة وصلة أو قياد — استخدمه في Authorization header</p>
      <div class="form-row">
        <div class="form-group"><label>المنتج (issuer)</label>
          <select id="tk-issuer"><option value="wasla">وصلة (wasla)</option><option value="qiad">قياد (qiad)</option></select>
        </div>
        <div class="form-group"><label>معرف المستخدم</label><input id="tk-sub" value="test-user" dir="ltr"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>معرف المنظمة</label><input id="tk-org" value="test-org" dir="ltr"></div>
        <div class="form-group"><label>مدة الصلاحية (ثواني)</label><input id="tk-ttl" type="number" value="3600"></div>
      </div>
      <div class="form-group"><label>الصلاحيات (مفصولة بفاصلة)</label><input id="tk-perms" value="store.generate,store.submit,store.view,merchants.view" dir="ltr"></div>
      <button class="btn" onclick="generateToken()">توليد التوكن</button>
      <div id="token-result"></div>
    </div>
  </div>

  <div id="panel-migrations" class="panel">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.75rem">
        <h2>حالة الجداول</h2>
        <button class="btn btn-outline" onclick="loadMigrations()">فحص</button>
      </div>
      <div id="migrations-body"><div class="empty">اضغط فحص لمراجعة الجداول</div></div>
    </div>
  </div>
</div>

<script>
const BASE = '/api/v1/admin';

function headers() {
  return {'Content-Type':'application/json'};
}

function showTab(id, btn) {
  document.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active')});
  document.querySelectorAll('.panel').forEach(function(p){p.classList.remove('active')});
  btn.classList.add('active');
  document.getElementById('panel-'+id).classList.add('active');
  if (id === 'config') loadConfig();
  if (id === 'tenants') loadTenants();
}

function pill(status) {
  if (status === 'ok') return '<span class="pill pill-ok">متصل</span>';
  if (status === 'missing') return '<span class="pill pill-warn">مفقود</span>';
  return '<span class="pill pill-err">خطأ</span>';
}

function loadHealth() {
  var el = document.getElementById('health-body');
  el.innerHTML = '<span class="spinner"></span>';
  fetch(BASE+'/health', {headers: headers()}).then(function(r){return r.json()}).then(function(d) {
    var html = '';
    for (var k in d.checks) {
      var v = d.checks[k];
      html += '<div class="row"><span class="row-label">'+k+'</span>'+pill(v.status)+'<span style="font-size:.78rem;color:var(--ink3)">'+v.message+'</span></div>';
    }
    el.innerHTML = html;
  }).catch(function(e) { el.innerHTML = '<div class="empty" style="color:var(--err)">فشل الاتصال: '+e.message+'</div>'; });
}

function testWaslak() {
  var el = document.getElementById('waslak-result');
  document.getElementById('btn-waslak').disabled = true;
  el.innerHTML = '<span class="spinner"></span>';
  fetch(BASE+'/test-waslak', {method:'POST', headers: headers()}).then(function(r){return r.json()}).then(function(d) {
    el.innerHTML = '<div class="result">'+JSON.stringify(d, null, 2)+'</div>';
  }).catch(function(e) { el.innerHTML = '<div class="result" style="color:var(--err)">'+e.message+'</div>'; });
  document.getElementById('btn-waslak').disabled = false;
}

function loadConfig() {
  var el = document.getElementById('config-body');
  fetch(BASE+'/config', {headers: headers()}).then(function(r){return r.json()}).then(function(d) {
    var html = '';
    for (var i = 0; i < d.config.length; i++) {
      var c = d.config[i];
      var p = c.set ? '<span class="pill pill-ok">مُعد</span>' : '<span class="pill pill-warn">غير مُعد</span>';
      var v = c.set ? '<span class="row-value">'+c.value+'</span>' : '';
      html += '<div class="row"><span class="row-label">'+c.label+'</span>'+p+v+'</div>';
    }
    el.innerHTML = html;
  }).catch(function(e) { el.innerHTML = '<div class="empty" style="color:var(--err)">'+e.message+'</div>'; });
}

function loadTenants() {
  var el = document.getElementById('tenants-list');
  fetch(BASE+'/tenant-config', {headers: headers()}).then(function(r){return r.json()}).then(function(d) {
    if (!d.tenants || d.tenants.length === 0) { el.innerHTML = '<div class="empty">لا يوجد مستأجرين مسجلين</div>'; return; }
    var html = '';
    for (var i = 0; i < d.tenants.length; i++) {
      var t = d.tenants[i];
      var st = t.enabled ? '<span class="pill pill-ok">مفعل</span>' : '<span class="pill pill-err">معطل</span>';
      html += '<div class="row"><span class="row-label">'+t.tenant_id+'</span>'+st+'<span style="font-size:.78rem;color:var(--ink3)">'+t.waslak_base_url+' &middot; '+t.max_drafts_per_hour+'/hr</span></div>';
    }
    el.innerHTML = html;
  }).catch(function(e) { el.innerHTML = '<div class="empty">'+e.message+'</div>'; });
}

function saveTenant() {
  var el = document.getElementById('tenant-save-result');
  var body = {
    tenant_id: document.getElementById('tc-tid').value,
    waslak_base_url: document.getElementById('tc-url').value,
    waslak_api_key: document.getElementById('tc-key').value,
    max_drafts_per_hour: parseInt(document.getElementById('tc-limit').value) || 30,
    enabled: true
  };
  if (!body.tenant_id || !body.waslak_base_url || !body.waslak_api_key) {
    el.innerHTML = '<div class="result" style="color:var(--err)">جميع الحقول مطلوبة</div>';
    return;
  }
  fetch(BASE+'/tenant-config', {method:'POST', headers:headers(), body:JSON.stringify(body)}).then(function(r){return r.json()}).then(function(d) {
    el.innerHTML = '<div class="result" style="color:var(--ok)">تم الحفظ: '+d.tenant_id+'</div>';
    loadTenants();
  }).catch(function(e) { el.innerHTML = '<div class="result" style="color:var(--err)">'+e.message+'</div>'; });
}

function generateToken() {
  var el = document.getElementById('token-result');
  var perms = document.getElementById('tk-perms').value.split(',').map(function(s){return s.trim()}).filter(Boolean);
  var body = {
    issuer: document.getElementById('tk-issuer').value,
    subject: document.getElementById('tk-sub').value,
    organization_id: document.getElementById('tk-org').value,
    permissions: perms,
    ttl_seconds: parseInt(document.getElementById('tk-ttl').value) || 3600
  };
  fetch(BASE+'/generate-token', {method:'POST', headers:headers(), body:JSON.stringify(body)}).then(function(r){return r.json()}).then(function(d) {
    if (d.error) { el.innerHTML = '<div class="result" style="color:var(--err)">'+d.error+'</div>'; return; }
    el.innerHTML = '<div class="result">// التوكن:\\n'+d.token+'\\n\\n// الاستخدام:\\ncurl -H "Authorization: Bearer '+d.token+'" \\\\\\n  http://localhost:8000/api/v1/wasla/projects\\n\\n// الصلاحية: '+d.expires_in+' ثانية</div>';
  }).catch(function(e) { el.innerHTML = '<div class="result" style="color:var(--err)">'+e.message+'</div>'; });
}

function loadMigrations() {
  var el = document.getElementById('migrations-body');
  el.innerHTML = '<span class="spinner"></span>';
  fetch(BASE+'/migrations', {headers:headers()}).then(function(r){return r.json()}).then(function(d) {
    var html = '';
    for (var i = 0; i < d.tables.length; i++) {
      var t = d.tables[i];
      var p = t.exists ? '<span class="pill pill-ok">موجود ('+t.rows+')</span>' : '<span class="pill pill-err">غير موجود</span>';
      html += '<div class="row"><span class="row-label" style="font-family:var(--mono);direction:ltr;text-align:left">'+t.table+'</span>'+p+'<span style="font-size:.72rem;color:var(--ink3)">'+t.migration+'</span></div>';
    }
    el.innerHTML = html;
  }).catch(function(e) { el.innerHTML = '<div class="empty" style="color:var(--err)">'+e.message+'</div>'; });
}
</script>
</body>
</html>"""
