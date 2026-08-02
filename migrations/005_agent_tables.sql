-- =====================================================================
-- Migration 005: Awab Personal AI Office — Agent Tables
-- Run once: psql $DATABASE_URL -f migrations/005_agent_tables.sql
-- =====================================================================

-- Tasks: every user request creates one task
CREATE TABLE IF NOT EXISTS ai_tasks (
    id              UUID PRIMARY KEY,
    user_id         TEXT NOT NULL DEFAULT 'awab',
    channel         TEXT NOT NULL DEFAULT 'telegram',
    message         TEXT NOT NULL,
    intent          TEXT,
    assigned_agent  TEXT,
    risk_level      TEXT CHECK (risk_level IN ('low','medium','high')),
    needs_approval  BOOLEAN DEFAULT FALSE,
    plan            JSONB DEFAULT '{}',
    output          JSONB,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_ai_tasks_status    ON ai_tasks (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_tasks_user      ON ai_tasks (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_tasks_intent    ON ai_tasks (intent);

-- Task steps: each agent call within a task
CREATE TABLE IF NOT EXISTS ai_task_steps (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id     UUID REFERENCES ai_tasks(id) ON DELETE CASCADE,
    step_index  INTEGER NOT NULL DEFAULT 0,
    agent_name  TEXT NOT NULL,
    input       JSONB DEFAULT '{}',
    output      JSONB,
    duration_ms INTEGER,
    status      TEXT DEFAULT 'pending',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_task_steps_task ON ai_task_steps (task_id, step_index);

-- Reviews: reviewer agent decision per task
CREATE TABLE IF NOT EXISTS ai_reviews (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id                 UUID UNIQUE REFERENCES ai_tasks(id) ON DELETE CASCADE,
    approved                BOOLEAN NOT NULL,
    final_answer            TEXT,
    issues                  JSONB DEFAULT '[]',
    needs_user_confirmation BOOLEAN DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Email drafts: never-sent, always needs approval
CREATE TABLE IF NOT EXISTS email_drafts (
    id              UUID PRIMARY KEY,
    task_id         UUID REFERENCES ai_tasks(id) ON DELETE SET NULL,
    to_email        TEXT,
    subject         TEXT,
    draft_body      TEXT NOT NULL,
    summary         TEXT,
    risk_notes      JSONB DEFAULT '[]',
    approval_status TEXT NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_email_drafts_status ON email_drafts (approval_status, created_at DESC);

-- Olivery reports: cached report results
CREATE TABLE IF NOT EXISTS olivery_reports (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id     UUID REFERENCES ai_tasks(id) ON DELETE SET NULL,
    report_type TEXT NOT NULL,
    filters     JSONB DEFAULT '{}',
    summary     TEXT,
    rows        JSONB DEFAULT '[]',
    row_count   INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_olivery_reports_type ON olivery_reports (report_type, created_at DESC);

-- File artifacts: analysis results for uploaded files
CREATE TABLE IF NOT EXISTS file_artifacts (
    id          UUID PRIMARY KEY,
    task_id     UUID REFERENCES ai_tasks(id) ON DELETE SET NULL,
    file_name   TEXT,
    mime_type   TEXT,
    summary     TEXT,
    key_points  JSONB DEFAULT '[]',
    actions     JSONB DEFAULT '[]',
    risk_notes  JSONB DEFAULT '[]',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Audit log: immutable record of all agent actions
CREATE TABLE IF NOT EXISTS audit_log (
    id          UUID PRIMARY KEY,
    task_id     UUID,
    action      TEXT NOT NULL,
    payload     JSONB DEFAULT '{}',
    status      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_task   ON audit_log (task_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log (action, created_at DESC);
