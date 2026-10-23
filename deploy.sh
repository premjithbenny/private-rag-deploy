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
echo "Deployment started."
echo "Open WebUI: http://<SERVER-IP>:3000"
echo "Check status: ./status.sh"
