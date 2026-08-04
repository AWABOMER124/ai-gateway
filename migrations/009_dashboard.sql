-- =====================================================================
-- Migration 009: Dashboard — team accounts, integration API keys, skill
-- readiness test runs
-- Run: ./scripts/run_migrations.sh (tracked in schema_migrations, safe to re-run)
-- =====================================================================

-- Small-team dashboard login. No self-signup — accounts are created by an
-- owner via scripts/create_dashboard_user.py.
CREATE TABLE IF NOT EXISTS dashboard_users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,             -- 'pbkdf2_sha256$<iters>$<salt_hex>$<hash_hex>'
    role          TEXT NOT NULL DEFAULT 'member',  -- 'owner' | 'member'
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dashboard_users_email ON dashboard_users (email);

-- Scoped, revocable integration API keys — the inbound-integration
-- replacement/complement to the single shared GATEWAY_API_KEY. Only a
-- SHA-256 hash of the key is ever stored; the raw value is shown once at
-- creation time in the dashboard.
CREATE TABLE IF NOT EXISTS integration_api_keys (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL,               -- human label, e.g. "n8n prod"
    key_prefix   TEXT NOT NULL,                -- first ~16 chars, shown in UI for identification
    key_hash     TEXT NOT NULL,                -- sha256 hex digest of the full key
    scopes       JSONB NOT NULL DEFAULT '[]',  -- e.g. ["waslak:draft","waslak:read"]
    created_by   UUID REFERENCES dashboard_users(id) ON DELETE SET NULL,
    revoked_at   TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_integration_api_keys_hash ON integration_api_keys (key_hash);
CREATE INDEX IF NOT EXISTS idx_integration_api_keys_active
    ON integration_api_keys (revoked_at) WHERE revoked_at IS NULL;

-- Skill readiness: one row per health-check or capability-test run, for the
-- 3 categories (design / ecommerce / learning) surfaced on the dashboard's
-- skill readiness page.
CREATE TABLE IF NOT EXISTS skill_test_runs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_code     TEXT NOT NULL,              -- 'design' | 'ecommerce' | 'learning'
    check_type     TEXT NOT NULL,              -- 'health' | 'capability'
    passed         BOOLEAN NOT NULL,
    score          NUMERIC(4,1),               -- 0-10 LLM-judge score; NULL for health checks
    summary        TEXT,                       -- one-line human summary
    output_excerpt TEXT,                       -- truncated raw output, for debugging
    triggered_by   UUID REFERENCES dashboard_users(id) ON DELETE SET NULL,  -- NULL = system
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_skill_test_runs_skill_created ON skill_test_runs (skill_code, created_at DESC);
