#!/usr/bin/env bash
# Post-deploy smoke: verify A2A surface on the deployed URL.
set -euo pipefail

APP="${1:-oldman-agent}"
URL="https://${APP}.fly.dev"

echo "→ Checking ${URL}/.well-known/agent-card.json"
CARD=$(curl -sf "${URL}/.well-known/agent-card.json")
NAME=$(echo "$CARD" | python3 -c "import sys, json; print(json.load(sys.stdin)['name'])")
URL_FIELD=$(echo "$CARD" | python3 -c "import sys, json; print(json.load(sys.stdin).get('url',''))")

echo "  name: $NAME"
echo "  url: $URL_FIELD"
if [ "$URL_FIELD" != "$URL" ]; then
  echo "✗ card url ($URL_FIELD) ≠ deploy URL ($URL)"
  exit 1
fi

echo "→ Running SDK-style client against ${URL}..."
python3 scripts/dummy_a2a_client.py "$URL"

echo "✓ deployed A2A agent reachable + spec-compliant"
