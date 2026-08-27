-- Migration 011: Conversation memory (3-layer architecture)
-- Layer 2: conversation summaries
-- Layer 3: structured customer memory
-- AI run logging for audit trail

-- ── Conversation summaries (Layer 2) ─────────────────────────────

CREATE TABLE IF NOT EXISTS ai_conversation_summaries (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL DEFAULT 'legacy',
    conversation_id TEXT NOT NULL,
    summary         TEXT NOT NULL,
    message_count   INTEGER NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_conv_summary UNIQUE (tenant_id, conversation_id)
);

CREATE INDEX IF NOT EXISTS idx_conv_summary_tenant
    ON ai_conversation_summaries (tenant_id, conversation_id);

-- ── Structured customer memory (Layer 3) ─────────────────────────

CREATE TABLE IF NOT EXISTS ai_customer_memory (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL DEFAULT 'legacy',
    customer_id TEXT NOT NULL,
    memory      JSONB NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_customer_memory UNIQUE (tenant_id, customer_id)
);

CREATE INDEX IF NOT EXISTS idx_customer_memory_tenant
    ON ai_customer_memory (tenant_id, customer_id);

-- ── AI run log (tracks every agent execution) ────────────────────

CREATE TABLE IF NOT EXISTS ai_runs (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL DEFAULT 'legacy',
    product         TEXT NOT NULL,
    agent_type      TEXT NOT NULL,           -- support, supervisor, reviewer, etc.
    conversation_id TEXT,
    customer_id     TEXT,
    actor_id        TEXT NOT NULL,
    agent_mode      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'started',  -- started, completed, failed
    action_taken    TEXT,                    -- reply, draft, handoff, error
    confidence      REAL,
    input_summary   TEXT,                    -- compressed input (no raw PII)
    output_summary  TEXT,                    -- compressed output
    tools_called    JSONB DEFAULT '[]',      -- list of tool keys used
    token_usage     JSONB DEFAULT '{}',      -- {prompt_tokens, completion_tokens, model}
    elapsed_ms      INTEGER,
    error_message   TEXT,
    request_id      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_runs_tenant
    ON ai_runs (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_runs_conversation
    ON ai_runs (conversation_id, created_at DESC)
    WHERE conversation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ai_runs_customer
    ON ai_runs (tenant_id, customer_id, created_at DESC)
    WHERE customer_id IS NOT NULL;
