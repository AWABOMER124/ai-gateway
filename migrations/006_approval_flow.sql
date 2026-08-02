-- =====================================================================
-- Migration 006: Approval flow — channel_ref lookup + Olivery edit staging
-- Run once: psql $DATABASE_URL -f migrations/006_approval_flow.sql
-- =====================================================================

-- channel_ref lets n8n ask "is there a pending approval for this chat?"
-- without depending on user_id (single-user today, but chat-scoped is correct).
ALTER TABLE ai_tasks ADD COLUMN IF NOT EXISTS channel_ref TEXT;
CREATE INDEX IF NOT EXISTS idx_ai_tasks_channel_ref ON ai_tasks (channel_ref, status);

-- Olivery edit requests: staged writes, never applied until Awab approves.
CREATE TABLE IF NOT EXISTS olivery_edit_requests (
    id              UUID PRIMARY KEY,
    task_id         UUID REFERENCES ai_tasks(id) ON DELETE CASCADE,
    order_id        TEXT NOT NULL,
    vals            JSONB NOT NULL DEFAULT '{}',
    preview         TEXT,
    approval_status TEXT NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_olivery_edit_requests_task   ON olivery_edit_requests (task_id);
CREATE INDEX IF NOT EXISTS idx_olivery_edit_requests_status ON olivery_edit_requests (approval_status, created_at DESC);
