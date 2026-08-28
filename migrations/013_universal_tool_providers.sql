-- Migration 013: Universal Tool Providers
-- Tables for provider management, capability mapping, tenant preferences, and execution logging.

-- ── Provider registry (persisted metadata) ──────────────────────────
CREATE TABLE IF NOT EXISTS ai_providers (
    key             TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    auth_type       TEXT NOT NULL DEFAULT 'api_key',
    base_url        TEXT NOT NULL DEFAULT '',
    enabled         BOOLEAN NOT NULL DEFAULT true,
    priority        INTEGER NOT NULL DEFAULT 100,
    timeout_seconds INTEGER NOT NULL DEFAULT 10,
    rate_limit_rpm  INTEGER,
    cost_per_call   NUMERIC(10,6) NOT NULL DEFAULT 0,
    data_class      TEXT NOT NULL DEFAULT 'public',
    config          JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Capabilities each provider supports ─────────────────────────────
CREATE TABLE IF NOT EXISTS ai_provider_capabilities (
    id              TEXT PRIMARY KEY,
    provider_key    TEXT NOT NULL REFERENCES ai_providers(key) ON DELETE CASCADE,
    capability      TEXT NOT NULL,
    supported_countries TEXT[] NOT NULL DEFAULT '{}',
    priority_override INTEGER,
    config          JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_provider_capability UNIQUE (provider_key, capability)
);

CREATE INDEX IF NOT EXISTS idx_ai_prov_cap_capability ON ai_provider_capabilities (capability);

-- ── Tenant-level provider preferences ───────────────────────────────
CREATE TABLE IF NOT EXISTS ai_tenant_provider_preferences (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL REFERENCES ai_tenants(id) ON DELETE CASCADE,
    capability      TEXT NOT NULL,
    preferred_provider TEXT REFERENCES ai_providers(key),
    blocked_providers  TEXT[] NOT NULL DEFAULT '{}',
    config          JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_tenant_cap_pref UNIQUE (tenant_id, capability)
);

-- ── Provider execution log ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_provider_executions (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL DEFAULT 'legacy',
    product         TEXT NOT NULL,
    capability      TEXT NOT NULL,
    provider_key    TEXT NOT NULL,
    status          TEXT NOT NULL,
    elapsed_ms      INTEGER,
    http_status     INTEGER,
    cached          BOOLEAN NOT NULL DEFAULT false,
    error_message   TEXT,
    request_id      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_prov_exec_tenant ON ai_provider_executions (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_prov_exec_provider ON ai_provider_executions (provider_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_prov_exec_capability ON ai_provider_executions (capability, created_at DESC);

-- ── Seed free providers ─────────────────────────────────────────────
INSERT INTO ai_providers (key, display_name, auth_type, base_url, priority, cost_per_call)
VALUES
    ('open_meteo', 'Open-Meteo', 'none', 'https://api.open-meteo.com', 10, 0),
    ('exchangerate_api', 'ExchangeRate-API', 'none', 'https://open.er-api.com', 10, 0)
ON CONFLICT (key) DO NOTHING;

INSERT INTO ai_provider_capabilities (id, provider_key, capability)
VALUES
    ('open_meteo_weather_current',  'open_meteo', 'weather.current'),
    ('open_meteo_weather_forecast', 'open_meteo', 'weather.forecast'),
    ('exchangerate_currency',       'exchangerate_api', 'currency.convert')
ON CONFLICT (provider_key, capability) DO NOTHING;
