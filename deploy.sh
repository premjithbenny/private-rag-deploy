#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is not installed."
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: Docker Compose plugin is unavailable."
  exit 1
fi

if [ ! -f .env ]; then
  if [ ! -f .env.example ]; then
    echo "ERROR: .env.example is missing."
    exit 1
  fi
  cp .env.example .env
  chmod 600 .env
fi

if ! grep -q '^WEBUI_SECRET_KEY=.' .env; then
  python3 - <<'PY'
import secrets
from pathlib import Path

p = Path(".env")
lines = p.read_text().splitlines() if p.exists() else []
lines = [line for line in lines if not line.startswith("WEBUI_SECRET_KEY=")]
lines.append("WEBUI_SECRET_KEY=" + secrets.token_hex(32))
p.write_text("\n".join(lines) + "\n")
p.chmod(0o600)
PY
fi

COMPOSE=(
  docker compose
  --project-name private-rag
  --env-file "$ROOT/.env"
  -f "$ROOT/opea/compose.yaml"
  -f "$ROOT/opea/compose.vllm.override.yaml"
  -f "$ROOT/compose.app.yaml"
)

echo "Validating deployment configuration..."
"${COMPOSE[@]}" config --quiet

echo "Starting Private RAG services..."
"${COMPOSE[@]}" up -d --build

echo
echo "Waiting for vLLM API (model download/loading can take several minutes)..."
ready=0
for i in $(seq 1 180); do
  if curl --fail --silent --show-error --max-time 5 \
      http://127.0.0.1:8000/v1/models >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 10
done

if [ "$ready" -ne 1 ]; then
  echo "ERROR: vLLM did not become ready within 30 minutes."
  echo "Recent vLLM logs:"
  docker logs --tail 100 private-rag-rag-llm-1 2>&1 || true
  exit 1
fi

echo "vLLM API is responding."
echo "Checking data-preparation health..."
if ! curl --fail --silent --show-error --max-time 10 \
    http://127.0.0.1:6007/v1/health_check; then
  echo
  echo "ERROR: Data-preparation health check failed."
  "${COMPOSE[@]}" ps
  exit 1
fi

echo
echo "Initial readiness checks passed."
echo "Open WebUI: http://<SERVER-IP>:3000"
echo "Check status: ./status.sh"
"${COMPOSE[@]}" ps
