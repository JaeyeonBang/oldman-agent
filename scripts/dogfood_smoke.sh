#!/usr/bin/env bash
# dogfood_smoke.sh — oldman_agent v1 dogfood smoke test
#
# 사용법:
#   BASE=http://localhost:8080 bash scripts/dogfood_smoke.sh
#
# Docker Compose 기동 후 실행:
#   docker compose up -d
#   bash scripts/dogfood_smoke.sh
#
# 종료 코드: 0=PASS, 1=FAIL

set -euo pipefail

BASE="${BASE:-http://localhost:8080}"
PASS=0
FAIL=0

_ok()   { echo "[OK]   $*"; PASS=$((PASS+1)); }
_fail() { echo "[FAIL] $*"; FAIL=$((FAIL+1)); }
_info() { echo "[INFO] $*"; }

# ── 1. /health 폴링 (최대 30초) ───────────────────────────────────────────────
_info "Waiting for $BASE/health ..."
for i in $(seq 1 30); do
    if curl -sf "$BASE/health" > /dev/null 2>&1; then
        _ok "/health returned 200 (attempt $i)"
        break
    fi
    if [ "$i" -eq 30 ]; then
        _fail "/health did not respond within 30s"
        exit 1
    fi
    sleep 1
done

# ── 2. /publish × 10 ─────────────────────────────────────────────────────────
_info "Publishing 10 events ..."
for i in $(seq 0 9); do
    if [ $((i % 2)) -eq 0 ]; then
        AGENT="agent_alice"
        OBS="agent_bob"
    else
        AGENT="agent_bob"
        OBS="agent_alice"
    fi

    PAYLOAD=$(printf '{"event_kind":"observation","source_agent":"%s","observed_agent":"%s","declared_source_type":"third_party","payload":{"msg":"dogfood smoke event %d","ts":"%s"}}' \
        "$AGENT" "$OBS" "$i" "$(date -u +%Y-%m-%dT%H:%M:%SZ)")

    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$PAYLOAD" \
        "$BASE/publish")

    if [ "$HTTP_STATUS" -eq 200 ]; then
        _ok "publish[$i] → 200 stored"
    else
        _fail "publish[$i] → unexpected HTTP $HTTP_STATUS"
    fi
done

# ── 3. reflection 대기 ────────────────────────────────────────────────────────
_info "Waiting 3s for background reflections ..."
sleep 3

# ── 4. /query — strict_mode=false (mock judge safe) ──────────────────────────
_info "Querying /query ..."
QUERY_PAYLOAD='{"question":"agent_alice가 최근 어떤 행동을 보였나요?","subject_agent":"agent_alice","strict_mode":false}'

QUERY_RESPONSE=$(curl -s -w "\n__HTTP_STATUS__:%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d "$QUERY_PAYLOAD" \
    "$BASE/query")

HTTP_STATUS=$(echo "$QUERY_RESPONSE" | grep "__HTTP_STATUS__:" | sed 's/__HTTP_STATUS__://')
BODY=$(echo "$QUERY_RESPONSE" | grep -v "__HTTP_STATUS__:")

if [ "$HTTP_STATUS" -eq 200 ]; then
    _ok "/query → 200"
else
    _fail "/query → unexpected HTTP $HTTP_STATUS"
    echo "$BODY"
    exit 1
fi

# ── 5. 응답 검증 ─────────────────────────────────────────────────────────────
# jq가 있으면 정밀 파싱, 없으면 grep 기반 존재 확인
if command -v jq > /dev/null 2>&1; then
    ANSWER=$(echo "$BODY" | jq -r '.answer // ""')
    CITATIONS_LEN=$(echo "$BODY" | jq '.citations | length')
    IS_COLD_START=$(echo "$BODY" | jq -r '.is_cold_start')

    if [ -n "$ANSWER" ] && [ "$ANSWER" != "null" ]; then
        _ok "answer non-empty (${#ANSWER} chars)"
    else
        _fail "answer is empty or null"
    fi

    if [ "$CITATIONS_LEN" -gt 0 ]; then
        _ok "citations non-empty ($CITATIONS_LEN items)"
    else
        # cold-start 또는 reflection 미완료 시 citations가 0일 수 있음 — 경고만
        if [ "$IS_COLD_START" = "true" ]; then
            _info "citations empty but is_cold_start=true (reflection not yet triggered — OK for smoke)"
            _ok "cold-start acknowledged"
        else
            _fail "citations empty and is_cold_start=false"
        fi
    fi
else
    # jq 없음 — grep으로 존재 확인
    if echo "$BODY" | grep -q '"answer"'; then
        _ok "answer field present in response"
    else
        _fail "answer field missing from response"
    fi

    if echo "$BODY" | grep -q '"citations"'; then
        _ok "citations field present in response"
    else
        _fail "citations field missing from response"
    fi
fi

# ── 6. 요약 ──────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  dogfood smoke: PASS=$PASS  FAIL=$FAIL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
