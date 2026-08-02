-- =====================================================================
-- Migration 007: Waslak Merchant OS integration — store draft staging + insights
-- Run once: psql $DATABASE_URL -f migrations/007_waslak.sql
-- =====================================================================

-- Waslak store draft requests: staged locally first, never sent to Waslak until Awab
-- approves via /approvals/decide. Once approved+executed, waslak_draft_id/waslak_status/
-- merchant_id/rejection_reason get filled in from Waslak's response, and kept fresh by
-- polling GET /waslak/store-draft/{id} (Waslak has no webhook).
CREATE TABLE IF NOT EXISTS waslak_store_drafts (
    id                UUID PRIMARY KEY,
    task_id           UUID REFERENCES ai_tasks(id) ON DELETE SET NULL,
    prompt            TEXT NOT NULL,
    business_type     TEXT,
    payload           JSONB NOT NULL DEFAULT '{}',
    validation_errors JSONB DEFAULT '[]',
    approval_status   TEXT NOT NULL DEFAULT 'pending', -- pending|approved|rejected|executed|execution_failed
    waslak_draft_id   TEXT,
    waslak_status     TEXT,                            -- PENDING|APPROVED|REJECTED (mirrors Waslak's status)
    merchant_id       TEXT,
    rejection_reason  TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_waslak_store_drafts_task      ON waslak_store_drafts (task_id);
CREATE INDEX IF NOT EXISTS idx_waslak_store_drafts_status    ON waslak_store_drafts (approval_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_waslak_store_drafts_waslak_id ON waslak_store_drafts (waslak_draft_id);

-- Waslak insights: persisted read-only reports (merchant order-status counts + GPT
-- suggestions). Persisted synchronously in the same request that generates them — no
-- approval needed (read-only against Waslak), but must never be generate-and-forget.
CREATE TABLE IF NOT EXISTS waslak_insights (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id       UUID REFERENCES ai_tasks(id) ON DELETE SET NULL,
    merchant_id   TEXT NOT NULL,
    order_summary JSONB NOT NULL DEFAULT '{}',
    suggestions   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_waslak_insights_merchant ON waslak_insights (merchant_id, created_at DESC);
