#!/usr/bin/env bash
# Deploy to Fly.io.  Run from project root.
# Prerequisites: `fly auth login`, app + volume already created.
set -euo pipefail

APP="${1:-oldman-agent}"

echo "→ Deploying ${APP}..."
fly deploy --app "$APP"

echo "→ Post-deploy verify..."
./scripts/post_deploy_verify.sh "$APP"
