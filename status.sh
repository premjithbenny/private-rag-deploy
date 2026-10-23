#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

docker compose \
  --project-name private-rag \
  --env-file "$ROOT/.env" \
  -f "$ROOT/opea/compose.yaml" \
  -f "$ROOT/opea/compose.vllm.override.yaml" \
  -f "$ROOT/compose.app.yaml" \
  ps
