# AI Platform Architecture Baseline

Generated from full codebase inspection of `ai-gateway` (commit on `main` branch).

---

## CONFIRMED

### Current Identity
- **Name:** "Awab AI Operator — API Gateway" / "Awab Personal AI Office"
- **Framework:** FastAPI (Python 3.11), uvicorn, Docker
- **Database:** PostgreSQL + pgvector, psycopg2 with ThreadedConnectionPool (max 10)
- **AI Provider:** OpenAI only (gpt-4.1-mini default, text-embedding-3-small)
- **Auth:** Legacy shared `GATEWAY_API_KEY` + scoped integration API keys (SHA-256 hashed)
- **Tenancy:** Single-tenant (hardcoded `user_id: "awab"`, no tenant concept)

### Agent Architecture
- **Supervisor:** Intent classification → agent assignment → risk assessment (JSON output)
- **Reviewer:** Quality gate before execution (mandatory since 2026-08-03)
- **Executor:** Gated action execution (send_email, update_order_status, submit_waslak_draft)
- **Knowledge Agent:** RAG via pgvector (ai_chunks table)
- **Email Agent:** Draft professional replies
- **Olivery Agent:** EasyDelivery operational reports + order edits
- **File Agent:** Analyze uploaded files (Excel, PDF, image)
- **Writing Agent:** Business documents, proposals
- **Waslak Agent:** StoreDraft generation + merchant insights

### Approval Flow
- All medium/high risk actions require human approval
- `/approvals/decide` triggers mandatory Reviewer gate before Executor
- Immutable audit_log records every action

### Database Tables (5 migrations: 005-009)
- `ai_tasks`, `ai_task_steps`, `ai_reviews` — task lifecycle
- `email_drafts` — staged email drafts
- `olivery_reports`, `olivery_edit_requests` — EasyDelivery data
- `file_artifacts` — file analysis results
- `audit_log` — immutable action log
- `waslak_store_drafts` — staged store drafts
- `waslak_insights` — merchant analytics
- `openai_usage_log` — spend tracking with daily cap
- `dashboard_users`, `integration_api_keys` — auth
- `skill_test_runs` — skill readiness tests
- `schema_migrations` — migration tracker
- `ai_documents`, `ai_chunks` — RAG knowledge base (pre-existing, not in migrations/)

### External Integrations
- **Waslak/Wasla:** REST client for `/api/agent/v1/*` (stores:draft, merchants:read, orders:read)
- **Olivery/EasyDelivery:** REST client for operational data
- **SMTP:** Office365 for email sending
- **OpenAI:** Chat completions + embeddings

### Security Features
- Scoped API keys with per-scope enforcement
- PBKDF2-SHA256 password hashing (260K iterations)
- HMAC-signed session cookies
- Daily OpenAI spend cap ($10 default)
- Container resource limits (1GB RAM, 1 CPU)
- DB port bound to 127.0.0.1 only

---

## CURRENT ARCHITECTURE

```
Client (Telegram/n8n/curl)
    │
    ├── X-API-Key / Bearer token
    │
    ▼
FastAPI (app/main.py)
    │
    ├── /health
    ├── /ask, /search          ← RAG pipeline (legacy sync)
    ├── /agent/plan            ← Supervisor
    ├── /agent/review          ← Reviewer
    ├── /email/draft           ← Email Agent
    ├── /olivery/report        ← Olivery Agent
    ├── /olivery/edit-order    ← Olivery Agent (staged write)
    ├── /files/analyze-text    ← File Agent
    ├── /waslak/store-draft    ← Waslak Agent (staged)
    ├── /waslak/merchants      ← Waslak Client (read-only)
    ├── /waslak/merchants/*/insights ← Waslak Agent (analytics)
    ├── /approvals/*           ← Approval flow + Executor
    └── /dashboard/*           ← Team dashboard (Jinja2)
         │
         ▼
    PostgreSQL + pgvector
    (single database, no tenant isolation)
```

---

## EXISTING CAPABILITIES (Preserve These)

1. Supervisor → Agent → Reviewer → Approval → Executor pipeline
2. RAG vector search (ai_chunks + pgvector)
3. Scoped API keys with dashboard management
4. OpenAI spend tracking and daily cap
5. Audit logging (immutable append-only)
6. Waslak StoreDraft generation with validation
7. Waslak merchant insights (order analytics + GPT suggestions)
8. Olivery reports and staged order edits
9. Email drafting with approval gate
10. File analysis
11. Skill readiness testing (health + capability with LLM judge)
12. Docker deployment with resource limits

---

## GAPS (Required for Multi-Tenant AI Core)

### P0 — Critical
1. **No tenant concept** — everything is single-user ("awab"), no `tenant_id` anywhere
2. **No ExecutionContext** — no structured request context propagation
3. **No product abstraction** — agents hardcoded to specific products (Olivery, Waslak)
4. **No tool registry** — agents call functions directly, no permission/policy layer
5. **No risk policy engine** — risk is a string from LLM, no enforcement framework
6. **No service-to-service auth** — QIAD would need verified tenant claims, not just API key
7. **No tenant data isolation** — all tables lack `tenant_id`, no row-level filtering

### P1 — Important
8. **No conversation memory** — each request is stateless, no conversation/customer context
9. **No model routing** — hardcoded to single OpenAI model
10. **No structured agent output** — agents return free-text parsed as JSON
11. **No handoff protocol** — no standardized human escalation
12. **No rate limiting** — beyond OpenAI spend cap, no per-tenant/endpoint limits
13. **No idempotency** — no duplicate request prevention
14. **No event contracts** — no standardized event format

### P2 — Enhancement
15. **No agent versioning** — prompt changes are untracked
16. **No confidence scoring framework** — confidence is a string from LLM
17. **No context budgeting** — full context sent to model every time

---

## DUPLICATION (Between QIAD and AI Gateway)

Based on the prompt's description of QIAD (cannot inspect directly — private repo):

| Capability | ai-gateway | QIAD (described) |
|---|---|---|
| Knowledge/RAG | pgvector in ai_chunks | Organization-scoped knowledge system |
| AI Provider | OpenAI only | OpenAI + Google models |
| Token Tracking | openai_usage_log | AI token quotas per org |
| Agent Concept | Supervisor/agents | AI agents per organization |
| Conversation | None (stateless) | Conversation model with summaries |
| Auth | API keys + dashboard | Supabase Auth + RLS |
| Multi-tenancy | None | Full (organizations + RLS) |

**Risk:** Building duplicate knowledge stores and AI tracking without clear ownership boundary.

---

## SECURITY RISKS

1. **No tenant isolation at all** — single-tenant system, any API key sees everything
2. **LLM-generated intent controls execution path** — supervisor output directly selects agent
3. **Knowledge base has no access control** — all chunks visible to all queries
4. **Tool execution not permission-gated** — executor checks action_type, not caller permissions
5. **Audit log silently swallows errors** — `except Exception: pass` in `_log_sync`
6. **CORS allows all origins** — `allow_origins=['*']`
7. **Persona hardcoded** — "Awab's AI Chief of Staff for EasyDelivery" in system prompts

---

## COMPATIBILITY RISKS

1. Legacy `/ask`, `/search` use sync `db_cursor()` (not pooled) — still works but different path
2. Legacy `GATEWAY_API_KEY` must continue working (full access)
3. n8n/Telegram workflows depend on exact response shapes
4. Waslak API has 30 drafts/hour rate limit — must preserve throttling
5. Docker deployment on shared server with Waslak production

---

## IMPLEMENTATION PLAN

### Phase 1A — Platform Foundation (this PR)
- `app/core/context.py` — ExecutionContext with tenant/product/actor
- `app/core/tenancy.py` — Tenant registry and verification
- `app/core/security.py` — Service-to-service JWT verification
- `app/core/errors.py` — Standardized error types
- `app/core/policies.py` — Risk classification and policy engine
- `app/core/events.py` — Event contract definitions
- `app/tools/registry.py` — Tool definition and registry
- `app/tools/policy.py` — Tool permission and approval checks
- `app/tools/executor.py` — Safe tool execution with audit
- `app/integrations/qiad/adapter.py` — QIAD adapter interface
- `app/integrations/wasla/adapter.py` — Wasla adapter (wraps existing Waslak)
- `app/api/v1/router.py` — Versioned API with tenant context
- Migration 010 — Multi-tenant schema additions

### Phase 1B — QIAD Integration
- QIAD read-only tools (customer, conversation, knowledge, order)
- Support Agent with intent classification
- Handoff protocol
- Conversation memory (3-layer)

### Phase 1C — Safe Actions
- Outbound message tool with policy enforcement
- Approval integration with agent mode
- Idempotency keys

### Phase 1D — Wasla Foundation
- Store Project domain model (replaces single-draft)
- Version/patch mechanism
- Enhanced store specification
