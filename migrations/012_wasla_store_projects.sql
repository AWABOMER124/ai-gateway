-- Migration 012: Wasla Store Project V2
-- Replaces single-draft model with versioned store projects.
-- A project holds multiple versions (drafts), each version can have patches.
-- tenant_id enables multi-tenant isolation.

-- ── Store Projects ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS wasla_store_projects (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL DEFAULT 'legacy',
    merchant_id     TEXT,
    name            TEXT NOT NULL,
    description     TEXT,
    business_type   TEXT,
    style           JSONB NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'draft',
    current_version INTEGER NOT NULL DEFAULT 1,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_by      TEXT NOT NULL DEFAULT 'system',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_wasla_projects_tenant
    ON wasla_store_projects (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_wasla_projects_merchant
    ON wasla_store_projects (tenant_id, merchant_id)
    WHERE merchant_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_wasla_projects_status
    ON wasla_store_projects (tenant_id, status);

-- ── Store Versions (drafts) ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS wasla_store_versions (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES wasla_store_projects(id) ON DELETE CASCADE,
    tenant_id       TEXT NOT NULL DEFAULT 'legacy',
    version_number  INTEGER NOT NULL DEFAULT 1,
    payload         JSONB NOT NULL DEFAULT '{}',
    prompt          TEXT,
    generation_model TEXT,
    validation_errors JSONB NOT NULL DEFAULT '[]',
    status          TEXT NOT NULL DEFAULT 'generated',
    waslak_draft_id TEXT,
    waslak_status   TEXT,
    rejection_reason TEXT,
    submitted_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_project_version UNIQUE (project_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_wasla_versions_project
    ON wasla_store_versions (project_id, version_number DESC);

-- ── Version Patches (incremental edits) ─────────────────────────────

CREATE TABLE IF NOT EXISTS wasla_store_patches (
    id              TEXT PRIMARY KEY,
    version_id      TEXT NOT NULL REFERENCES wasla_store_versions(id) ON DELETE CASCADE,
    tenant_id       TEXT NOT NULL DEFAULT 'legacy',
    patch_type      TEXT NOT NULL,
    patch_data      JSONB NOT NULL DEFAULT '{}',
    applied_by      TEXT NOT NULL DEFAULT 'system',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_wasla_patches_version
    ON wasla_store_patches (version_id, created_at);

-- ── Wasla Tenant Config ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS wasla_tenant_config (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL UNIQUE,
    waslak_base_url TEXT NOT NULL,
    waslak_api_key_encrypted TEXT NOT NULL,
    max_drafts_per_hour INTEGER NOT NULL DEFAULT 30,
    enabled         BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Migrate existing drafts → project model ─────────────────────────

DO $$ BEGIN
    INSERT INTO wasla_store_projects (id, tenant_id, name, business_type, status, created_at)
    SELECT
        id,
        COALESCE(tenant_id, 'legacy'),
        COALESCE(payload->>'name', 'Untitled Store'),
        business_type,
        CASE approval_status
            WHEN 'approved' THEN 'submitted'
            WHEN 'execution_failed' THEN 'rejected'
            ELSE 'draft'
        END,
        created_at
    FROM waslak_store_drafts
    ON CONFLICT (id) DO NOTHING;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

DO $$ BEGIN
    INSERT INTO wasla_store_versions (id, project_id, tenant_id, version_number, payload, prompt, validation_errors, status, waslak_draft_id, waslak_status, rejection_reason, created_at)
    SELECT
        id || '_v1',
        id,
        COALESCE(tenant_id, 'legacy'),
        1,
        COALESCE(payload, '{}'),
        prompt,
        COALESCE(validation_errors, '[]'),
        CASE approval_status
            WHEN 'approved' THEN 'submitted'
            WHEN 'execution_failed' THEN 'rejected'
            ELSE 'generated'
        END,
        waslak_draft_id,
        waslak_status,
        rejection_reason,
        created_at
    FROM waslak_store_drafts
    WHERE id IN (SELECT id FROM wasla_store_projects)
    ON CONFLICT (id) DO NOTHING;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;
