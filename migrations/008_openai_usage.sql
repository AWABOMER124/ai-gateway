-- =====================================================================
-- Migration 008: OpenAI usage log — spend visibility + daily cap enforcement
-- Run: ./scripts/run_migrations.sh (tracked in schema_migrations, safe to re-run)
-- =====================================================================

-- Every OpenAI call (chat completion or embedding) from any code path — the
-- agents layer's _openai_chat, and the RAG pipeline's generate_answer /
-- get_embedding — records one row here. Used to enforce OPENAI_DAILY_SPEND_LIMIT_USD
-- (app/services/openai_usage.py) and to give actual spend visibility, since
-- prior to this there was no cap and no log at all (audit finding, 2026-08-02).
CREATE TABLE IF NOT EXISTS openai_usage_log (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint          TEXT NOT NULL,   -- 'chat' | 'embedding'
    model             TEXT NOT NULL,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    total_tokens      INTEGER,
    estimated_cost_usd NUMERIC(10,6) NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_openai_usage_created_at ON openai_usage_log (created_at DESC);
