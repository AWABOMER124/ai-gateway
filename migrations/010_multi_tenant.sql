-- Migration 010: Multi-tenant platform foundation
-- Adds tenant registry, product enablement, and tenant_id to existing tables.
-- All changes are additive (no drops, no destructive changes).
-- Existing rows get tenant_id = 'legacy' for backward compatibility.

-- ── Tenant registry ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ai_tenants (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    source_product TEXT NOT NULL DEFAULT 'legacy_personal',
    external_id TEXT,                    -- external org ID from the product (e.g. Supabase org)
    enabled     BOOLEAN NOT NULL DEFAULT true,
    config      JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_tenants_external ON ai_tenants (external_id) WHERE external_id IS NOT NULL;

-- ── Product enablement per tenant ────────────────────────────────────

CREATE TABLE IF NOT EXISTS ai_tenant_products (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES ai_tenants(id),
    product     TEXT NOT NULL,           -- qiad, wasla, legacy_personal, easy_delivery
    enabled     BOOLEAN NOT NULL DEFAULT true,
    config      JSONB NOT NULL DEFAULT '{}',  -- product-specific config (agent_mode, policies, etc.)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_tenant_product UNIQUE (tenant_id, product)
);

CREATE INDEX IF NOT EXISTS idx_ai_tenant_products_tenant ON ai_tenant_products (tenant_id);

-- ── Add tenant_id to existing tables (nullable for backward compat) ──

-- ai_tasks
DO $$ BEGIN
    ALTER TABLE ai_tasks ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'legacy';
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

-- audit_log
DO $$ BEGIN
    ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'legacy';
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

-- waslak_store_drafts
DO $$ BEGIN
    ALTER TABLE waslak_store_drafts ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'legacy';
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

-- waslak_insights
DO $$ BEGIN
    ALTER TABLE waslak_insights ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'legacy';
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

-- openai_usage_log
DO $$ BEGIN
    ALTER TABLE openai_usage_log ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'legacy';
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

-- email_drafts
DO $$ BEGIN
    ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'legacy';
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

-- ── Tool execution log (for audit of tool calls through the registry) ──

CREATE TABLE IF NOT EXISTS ai_tool_executions (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL DEFAULT 'legacy',
    product         TEXT NOT NULL,
    tool_key        TEXT NOT NULL,
    risk_level      TEXT NOT NULL,
    policy_decision TEXT NOT NULL,       -- allow, draft, approval_required, denied
    actor_type      TEXT NOT NULL,
    actor_id        TEXT NOT NULL,
    agent_mode      TEXT,
    params_hash     TEXT,                -- SHA-256 of params for idempotency (no raw params stored)
    status          TEXT NOT NULL DEFAULT 'started',  -- started, succeeded, failed, timeout, drafted
    error_message   TEXT,
    elapsed_ms      INTEGER,
    request_id      TEXT,
    idempotency_key TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_tool_exec_tenant ON ai_tool_executions (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_tool_exec_tool ON ai_tool_executions (tool_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_tool_exec_idempotency ON ai_tool_executions (idempotency_key) WHERE idempotency_key IS NOT NULL;

-- ── Bootstrap legacy tenant ──────────────────────────────────────────

INSERT INTO ai_tenants (id, name, source_product, created_at)
VALUES ('legacy', 'Awab Personal Office', 'legacy_personal', now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO ai_tenant_products (id, tenant_id, product, created_at)
VALUES
    ('legacy_personal', 'legacy', 'legacy_personal', now()),
    ('legacy_qiad', 'legacy', 'qiad', now()),
    ('legacy_wasla', 'legacy', 'wasla', now()),
    ('legacy_easy_delivery', 'legacy', 'easy_delivery', now())
ON CONFLICT (tenant_id, product) DO NOTHING;
