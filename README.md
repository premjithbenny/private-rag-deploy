# Private RAG Platform

A Docker Compose deployment of OPEA ChatQnA, vLLM, and Open WebUI.

## Components

- vLLM serving Qwen2.5-7B-Instruct
- OPEA ChatQnA backend
- OPEA dataprep, retriever, Redis vector database
- Hugging Face TEI embedding and reranking services
- Open WebUI with a small OpenAI-compatible adapter

## Requirements

- Linux server with a supported NVIDIA GPU
- NVIDIA driver and NVIDIA Container Toolkit configured for Docker
- Docker Engine and Docker Compose plugin
- Git and Python 3
- Sufficient disk space for container images and model downloads

Verify GPU access before deployment:

    nvidia-smi
    docker compose version
    docker run --rm --gpus all ubuntu nvidia-smi

## Configure
cd /opt
git clone https://github.com/premjithbenny/private-rag-deploy.git
cd /opt/private-rag-deploy
Copy `.env.example` to `.env` if it does not already exist:

    cp .env.example .env
    chmod 600 .env

The deployment script generates `WEBUI_SECRET_KEY` if missing.

Set `HF_TOKEN` only if a model or download requires authentication.
Never commit `.env`.

## validate

 docker compose \
  --project-name private-rag \
  --env-file "$PWD/.env" \
  -f "$PWD/opea/compose.yaml" \
  -f "$PWD/opea/compose.vllm.override.yaml" \
  -f "$PWD/compose.app.yaml" \
  config --quiet

  
## IF WEB_UI SOCKET KEY Error Occurs
cd /opt/private-rag-deploy

python3 - <<'PY'
import secrets
from pathlib import Path

p = Path(".env")
lines = p.read_text().splitlines() if p.exists() else []

if not any(line.startswith("WEBUI_SECRET_KEY=") and line.split("=", 1)[1].strip()
           for line in lines):
    lines = [line for line in lines if not line.startswith("WEBUI_SECRET_KEY=")]
    lines.append("WEBUI_SECRET_KEY=" + secrets.token_hex(32))
    p.write_text("\n".join(lines) + "\n")

p.chmod(0o600)
print("WEBUI_SECRET_KEY is configured.")
PY

  
## Deploy

    ./deploy.sh


The first startup downloads container images and model files and may take time.

Open the UI at:

    http://SERVER-IP:3000

Restrict access to trusted users. For production, place the UI behind HTTPS and suitable authentication/network controls.

## Ingest Knowledge files (PDF)
    curl -X POST "http://127.0.0.1:6007/v1/dataprep/ingest" -F "files=@/root/handbook.pdf"


## Verify

    ./status.sh
    curl http://127.0.0.1:8000/v1/models
    curl http://127.0.0.1:6007/v1/health_check

## Stop

    ./stop.sh

This stops and removes containers but preserves named volumes.

## Data and reset behavior

A fresh deployment creates new volumes for Redis, Open WebUI, and the Hugging Face model cache. It does not import data from another server.

- `redis-data`: newly ingested documents and vector index
- `open-webui-data`: new WebUI users and chat history
- `hf-cache`: downloaded model files

Do not run `docker compose down -v` unless you intentionally want to delete this deployment's persistent volumes.

## Configuration files

- `opea/compose.yaml`: upstream OPEA service definitions
- `opea/compose.vllm.override.yaml`: vLLM integration and deployment network
- `compose.app.yaml`: vLLM, Open WebUI, adapter, and data volumes
- `adapter/`: OpenAI-compatible adapter source
- `.env.example`: non-secret configuration template

Review and pin container image versions before using this package for a long-lived production deployment.
