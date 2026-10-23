# Private RAG Platform

A Docker Compose deployment of OPEA ChatQnA, vLLM, and Open WebUI for running a private, self-hosted AI knowledge assistant.

## Components

- **LLM inference:** vLLM serving Qwen2.5-7B-Instruct
- **RAG backend:** OPEA ChatQnA
- **Document processing:** OPEA dataprep
- **Retrieval:** OPEA retriever with Redis vector database
- **Embeddings:** Hugging Face Text Embeddings Inference (TEI)
- **Reranking:** Hugging Face TEI reranking service
- **Web interface:** Open WebUI
- **API integration:** Lightweight OpenAI-compatible adapter

## Requirements

- Linux server with a supported NVIDIA GPU
- NVIDIA GPU driver and NVIDIA Container Toolkit configured for Docker
- Docker Engine and Docker Compose plugin
- Git and Python 3
- Sufficient disk space for container images, model downloads, and persistent data

### Verify Prerequisites

Check GPU availability, Docker Compose, and GPU access from a container:

```bash
nvidia-smi
docker compose version
docker run --rm --gpus all ubuntu nvidia-smi
```

## Installation and Configuration

### 1. Clone the Repository

```bash
cd /opt
git clone https://github.com/premjithbenny/private-rag-deploy.git
cd /opt/private-rag-deploy
```

### 2. Configure Environment Variables

Create the environment configuration file if it does not already exist:

```bash
cp .env.example .env
chmod 600 .env
```

Configure the required environment variables in `.env` according to your deployment requirements.

- The deployment script generates `WEBUI_SECRET_KEY` if it is missing.
- Set `HF_TOKEN` only if a model or download requires authentication.
- Never commit `.env` or other files containing secrets to Git.

### 3. Validate the Docker Compose Configuration

Run the following command to validate the merged Compose configuration before deployment:

```bash
docker compose \
  --project-name private-rag \
  --env-file "$PWD/.env" \
  -f "$PWD/opea/compose.yaml" \
  -f "$PWD/opea/compose.vllm.override.yaml" \
  -f "$PWD/compose.app.yaml" \
  config --quiet
```

If validation succeeds, Docker Compose exits without printing the resolved configuration.

### 4. Fix the Open WebUI Secret Key Error (If Needed)

If Open WebUI fails to start because `WEBUI_SECRET_KEY` is missing or empty, generate a new key:

```bash
cd /opt/private-rag-deploy

python3 - <<'PY'
import secrets
from pathlib import Path

p = Path(".env")
lines = p.read_text().splitlines() if p.exists() else []

if not any(
    line.startswith("WEBUI_SECRET_KEY=")
    and line.split("=", 1)[1].strip()
    for line in lines
):
    lines = [
        line for line in lines
        if not line.startswith("WEBUI_SECRET_KEY=")
    ]
    lines.append("WEBUI_SECRET_KEY=" + secrets.token_hex(32))
    p.write_text("\n".join(lines) + "\n")

p.chmod(0o600)
print("WEBUI_SECRET_KEY is configured.")
PY
```

This script preserves an existing non-empty key and generates a new one only when necessary.

## Deployment

Start the platform using the deployment script:

```bash
./deploy.sh
```

The first startup may take some time because Docker needs to download container images and the required AI models.

Once the services are running, open the web interface:

```text
http://SERVER-IP:3000
```

Replace `SERVER-IP` with the IP address of your deployment server.

**Security:** Restrict access to trusted users. For production deployments, use HTTPS and appropriate authentication and network access controls.

## Ingest Knowledge Documents

Upload a PDF document to the dataprep service:

```bash
curl -X POST "http://127.0.0.1:6007/v1/dataprep/ingest" \
  -F "files=@/root/handbook.pdf"
```

Replace `/root/handbook.pdf` with the path to your PDF file.

The document is submitted to the dataprep service for processing and ingestion into the retrieval pipeline.

## Verification

### Check Service Status

```bash
./status.sh
```

### Verify the vLLM API

List the models available through the vLLM OpenAI-compatible API:

```bash
curl http://127.0.0.1:8000/v1/models
```

### Verify the Dataprep Service

```bash
curl http://127.0.0.1:6007/v1/health_check
```

## Stop the Deployment

Stop the platform using:

```bash
./stop.sh
```

This script stops and removes the deployment's containers while preserving its named volumes, provided the script does not explicitly remove them.

## Persistent Data and Reset Behavior

A fresh deployment creates new named volumes for Redis, Open WebUI, and the Hugging Face model cache. It does not automatically import data from another server.

| Volume | Purpose |
|---|---|
| `redis-data` | Ingested documents and vector index |
| `open-webui-data` | Open WebUI users and chat history |
| `hf-cache` | Downloaded Hugging Face model files |

**Warning:** Do not run `docker compose down -v` unless you intentionally want to delete the deployment's persistent volumes.

Back up persistent data before performing maintenance, upgrades, or migrations.

## Configuration Files

| File or directory | Description |
|---|---|
| `opea/compose.yaml` | Upstream OPEA service definitions |
| `opea/compose.vllm.override.yaml` | vLLM integration and deployment network configuration |
| `compose.app.yaml` | vLLM, Open WebUI, adapter, and data volume definitions |
| `adapter/` | OpenAI-compatible adapter source code |
| `.env.example` | Non-secret environment configuration template |
| `deploy.sh` | Deployment startup script |
| `status.sh` | Service status checks |
| `stop.sh` | Deployment shutdown script |

## Production Recommendations

- Pin container image versions instead of relying on mutable tags.
- Secure the web interface with HTTPS, authentication, and network restrictions.
- Keep secrets out of Git and restrict access to `.env`.
- Back up persistent volumes and test restoration procedures.
- Monitor GPU utilization, memory consumption, disk space, and service health.
- Test upgrades and configuration changes before applying them to production deployments.

