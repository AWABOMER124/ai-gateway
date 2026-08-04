#!/bin/bash
# Post-deploy smoke test — turns the manual curl checklist used throughout
# the 2026-08 audit/deploy session into one repeatable script. Run this after
# every `docker compose up -d --build` instead of eyeballing a few endpoints
# by hand; it would have caught the missing-aiosmtplib crash loop and the
# unapplied-migration 500 immediately instead of by chance.
#
# Deliberately does NOT call /approvals/decide with approved=true — that
# triggers a REAL external side effect (send an email, submit a Waslak
# draft, edit an Olivery order). This script only exercises safe, read-only
# or locally-staged-only paths. Run the real approval flow manually when you
# actually want to test end-to-end execution.
set -uo pipefail
cd "$(dirname "$0")/.."

API_KEY=$(grep -E '^GATEWAY_API_KEY' .env | cut -d= -f2-)
BASE="http://localhost:8000"
FAILED=0

check() {
    local name="$1" expected="$2" actual="$3"
    if [ "$actual" = "$expected" ]; then
        echo "  OK   $name ($actual)"
    else
        echo "  FAIL $name (expected $expected, got $actual)"
        FAILED=1
    fi
}

echo "== Container =="
status=$(docker inspect awab-ai-gateway --format '{{.State.Health.Status}}' 2>/dev/null || echo "no-container")
check "container healthy" "healthy" "$status"

echo "== Core =="
code=$(curl -s -o /dev/null -w '%{http_code}' -m 10 "$BASE/health")
check "GET /health" "200" "$code"

echo "== Agent office (writes a task, no side effects) =="
code=$(curl -s -o /dev/null -w '%{http_code}' -m 15 -X POST "$BASE/agent/plan" \
    -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
    -d '{"message":"smoke test sanity check","channel":"telegram","user_id":"smoketest"}')
check "POST /agent/plan" "200" "$code"

echo "== Files agent (stateless analysis, no side effects) =="
code=$(curl -s -o /dev/null -w '%{http_code}' -m 15 -X POST "$BASE/files/analyze-text" \
    -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
    -d '{"file_name":"smoke.csv","mime_type":"text/csv","content":"a,b\n1,2","instruction":"summarize"}')
check "POST /files/analyze-text" "200" "$code"

echo "== Email agent (drafts only, never sends without approval) =="
code=$(curl -s -o /dev/null -w '%{http_code}' -m 15 -X POST "$BASE/email/draft" \
    -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
    -d '{"email_subject":"smoke","email_body":"smoke test","instruction":"acknowledge","language":"en","to_email":"smoketest@example.com"}')
check "POST /email/draft" "200" "$code"

echo "== Olivery (read-only report; skipped gracefully if not configured) =="
code=$(curl -s -o /dev/null -w '%{http_code}' -m 20 -X POST "$BASE/olivery/report" \
    -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
    -d '{"report_type":"operation_daily","filters":{"date":"'"$(date +%F)"'"}}')
check "POST /olivery/report" "200" "$code"

echo "== Waslak (read-only list; 503 is a config issue, not a code bug) =="
code=$(curl -s -o /dev/null -w '%{http_code}' -m 15 "$BASE/waslak/merchants" -H "X-API-Key: $API_KEY")
if [ "$code" = "200" ] || [ "$code" = "503" ]; then
    echo "  OK   GET /waslak/merchants ($code)"
    [ "$code" = "503" ] && echo "       (503 = WASLAK_BASE_URL/WASLAK_API_KEY not set — expected if unconfigured, not a bug)"
else
    echo "  FAIL GET /waslak/merchants (expected 200 or 503, got $code)"
    FAILED=1
fi

echo "== Waslak store-draft generation (local staging only, no Waslak call) =="
code=$(curl -s -o /dev/null -w '%{http_code}' -m 20 -X POST "$BASE/waslak/store-draft" \
    -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
    -d '{"prompt":"smoke test placeholder store","business_type":"ecommerce"}')
check "POST /waslak/store-draft" "200" "$code"

echo "== RAG pipeline (knowledge base + OpenAI, no auth header required) =="
code=$(curl -s -o /dev/null -w '%{http_code}' -m 20 -X POST "$BASE/ask" \
    -H "Content-Type: application/json" \
    -d '{"question":"ما هي قواعد الوكيل؟","top_k":3}')
check "POST /ask" "200" "$code"

echo "== Dashboard (unauthenticated reachability only — no real login, no capability-test spend) =="
code=$(curl -s -o /dev/null -w '%{http_code}' -m 10 "$BASE/dashboard/login")
check "GET /dashboard/login" "200" "$code"
code=$(curl -s -o /dev/null -w '%{http_code}' -m 10 "$BASE/dashboard")
check "GET /dashboard (no session -> redirect)" "302" "$code"

echo ""
if [ "$FAILED" = "0" ]; then
    echo "All smoke checks passed."
else
    echo "One or more smoke checks FAILED — see above."
fi
exit "$FAILED"
