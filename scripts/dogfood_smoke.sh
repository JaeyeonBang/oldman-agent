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

# ── 2. publish × 10 via JSON-RPC message/send ───────────────────────────────
_info "Publishing 10 events via JSON-RPC ..."
for i in $(seq 0 9); do
    if [ $((i % 2)) -eq 0 ]; then
        AGENT="agent_alice"
        OBS="agent_bob"
    else
        AGENT="agent_bob"
        OBS="agent_alice"
    fi

    MSG_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
    RPC_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
    PAYLOAD=$(printf '{"jsonrpc":"2.0","id":"%s","method":"message/send","params":{"message":{"kind":"message","message_id":"%s","role":"user","metadata":{"oldman.intent":"publish"},"parts":[{"kind":"data","data":{"event_kind":"observation","source_agent":"%s","observed_agent":"%s","declared_source_type":"third_party","payload":{"msg":"dogfood smoke event %d","ts":"%s"}}}]}}}' \
        "$RPC_ID" "$MSG_ID" "$AGENT" "$OBS" "$i" "$(date -u +%Y-%m-%dT%H:%M:%SZ)")

    BODY=$(curl -s -X POST -H "Content-Type: application/json" -d "$PAYLOAD" "$BASE/")
    if echo "$BODY" | grep -q '"status":"stored"'; then
        _ok "publish[$i] → stored"
    elif echo "$BODY" | grep -q '"error"'; then
        _fail "publish[$i] → JSON-RPC error: $BODY"
    else
        _fail "publish[$i] → unexpected: $BODY"
    fi
done

# ── 3. reflection 대기 ────────────────────────────────────────────────────────
_info "Waiting 3s for background reflections ..."
sleep 3

# ── 4. query via JSON-RPC message/send (strict_mode=false) ──────────────────
_info "Querying via JSON-RPC ..."
Q_MSG_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
Q_RPC_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
QUERY_PAYLOAD=$(printf '{"jsonrpc":"2.0","id":"%s","method":"message/send","params":{"message":{"kind":"message","message_id":"%s","role":"user","metadata":{"oldman.intent":"query"},"parts":[{"kind":"text","text":"agent_alice가 최근 어떤 행동을 보였나요?"},{"kind":"data","data":{"subject_agent":"agent_alice","strict_mode":false,"max_citations":10}}]}}}' \
    "$Q_RPC_ID" "$Q_MSG_ID")

QUERY_RESPONSE=$(curl -s -w "\n__HTTP_STATUS__:%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d "$QUERY_PAYLOAD" \
    "$BASE/")

HTTP_STATUS=$(echo "$QUERY_RESPONSE" | grep "__HTTP_STATUS__:" | sed 's/__HTTP_STATUS__://')
RPC_BODY=$(echo "$QUERY_RESPONSE" | grep -v "__HTTP_STATUS__:")

if [ "$HTTP_STATUS" -eq 200 ] && ! echo "$RPC_BODY" | grep -q '"error"'; then
    _ok "JSON-RPC query → 200"
else
    _fail "JSON-RPC query → HTTP $HTTP_STATUS body: $RPC_BODY"
    exit 1
fi

# ── 5. 응답 검증 ─────────────────────────────────────────────────────────────
# JSON-RPC envelope에서 artifacts → text/data parts 추출
if command -v jq > /dev/null 2>&1; then
    ANSWER=$(echo "$RPC_BODY" | jq -r '[.result.artifacts[]?.parts[]? | select(.kind=="text") | .text] | first // ""')
    META=$(echo "$RPC_BODY" | jq -c '[.result.artifacts[]?.parts[]? | select(.kind=="data") | .data] | first // {}')
    CITATIONS_LEN=$(echo "$META" | jq '.citations | length')
    IS_COLD_START=$(echo "$META" | jq -r '.is_cold_start // false')

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
    if echo "$RPC_BODY" | grep -q '"kind":"text"'; then
        _ok "narrative text part present in JSON-RPC response"
    else
        _fail "narrative text part missing from JSON-RPC response"
    fi

    if echo "$RPC_BODY" | grep -q '"citations"'; then
        _ok "citations field present in JSON-RPC response"
    else
        _fail "citations field missing from JSON-RPC response"
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
