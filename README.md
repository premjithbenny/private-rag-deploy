
# Ninth Dimension Private RAG Platform

A self-hosted private AI knowledge platform built with OPEA ChatQnA, vLLM, Redis, and Open WebUI. It includes a branded landing page where users can choose between the AI Assistant and the RAG Document Ingester.

## Components

| Component | Purpose | Access |
|---|---|---|
| vLLM | Serves Qwen2.5-7B-Instruct | `127.0.0.1:8000` |
| OPEA ChatQnA | RAG orchestration and question answering | Port `8888` |
| OPEA DataPrep | Document and URL ingestion | Port `6007` |
| Redis vector database | Stores indexed knowledge | Internal/trusted network |
| TEI embeddings | Embedding generation | Port `8090` |
| TEI reranking | Reranks retrieved passages | Port `8808` |
| Open WebUI | AI chat interface | Port `3000` |
| OpenAI-compatible adapter | Connects Open WebUI to OPEA ChatQnA | `127.0.0.1:8099` |
| Knowledge Manager | Uploads documents and imports public URLs | Port `8098` |
| Ninth Dimension portal | Landing page linking to the two UIs | Port `80` |

**Security:** Do not expose every service publicly. Restrict backend APIs, Redis, DataPrep, embeddings, and reranking to the server or a trusted network.

## Requirements

- Linux server with a supported NVIDIA GPU
- NVIDIA GPU driver and NVIDIA Container Toolkit
- Docker Engine and Docker Compose plugin
- Git, Python 3, `curl`, and `unzip`
- Sufficient disk space for container images and model weights
- Firewall access configured for the required application ports

Verify prerequisites:

```bash
nvidia-smi
docker --version
docker compose version
docker run --rm --gpus all ubuntu nvidia-smi
git --version
python3 --version
```

Fix any GPU or Docker errors before deploying.

## 1. Clone the Repository

```bash
cd /opt
git clone https://github.com/premjithbenny/private-rag-deploy.git
cd /opt/private-rag-deploy
```

If the repository already exists, enter it rather than cloning it again.

## 2. Configure Environment Variables

Create `.env` from the example if it does not exist:

```bash
test -f .env || cp .env.example .env
chmod 600 .env
```

Edit `.env` and configure the required variables.

Ensure `WEBUI_SECRET_KEY` is set to a strong, persistent value. The following script generates a key only if it is missing or empty:

```bash
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

Do not regenerate the secret on every deployment. Changing it can invalidate existing sessions.

Set `HF_TOKEN` only if your model or download configuration requires authentication.

**Never commit `.env` or other files containing secrets to Git.**

## 3. Verify Required Files

The repository should contain these files and directories:

```text
private-rag-deploy/
├── compose.app.yaml
├── deploy.sh
├── status.sh
├── stop.sh
├── .env.example
├── adapter/
├── knowledge-ui/
├── portal/
└── opea/
    ├── compose.yaml
    └── compose.vllm.override.yaml
```

Check the landing page and branding assets:

```bash
ls -la portal/
grep -nE 'favicon|ninth-dimension|logo' portal/index.html
```

The `portal/` directory must contain `index.html` and every logo or favicon referenced in the HTML.

## 4. Validate Docker Compose

Run the following command from `/opt/private-rag-deploy`:

```bash
docker compose \
  --project-name private-rag \
  --env-file "$PWD/.env" \
  -f "$PWD/opea/compose.yaml" \
  -f "$PWD/opea/compose.vllm.override.yaml" \
  -f "$PWD/compose.app.yaml" \
  config --quiet
```

If validation fails, fix the reported configuration error before deploying.

## 5. Deploy the Platform

Start the platform using the deployment script:

```bash
chmod +x deploy.sh status.sh stop.sh
./deploy.sh
```

Ensure `deploy.sh` includes all required services, including the Knowledge Manager and portal.

If the script does not start those services, use the merged Compose configuration:

```bash
docker compose \
  --project-name private-rag \
  --env-file "$PWD/.env" \
  -f "$PWD/opea/compose.yaml" \
  -f "$PWD/opea/compose.vllm.override.yaml" \
  -f "$PWD/compose.app.yaml" \
  up -d --build
```

The first startup may take time while Docker downloads images and vLLM loads the model.

**Do not use `docker compose down -v` for routine deployment or troubleshooting.** It can delete persistent volumes.

## 6. Access the Applications

Replace `SERVER-IP` with your server's public IP or hostname.

| Application | URL | Purpose |
|---|---|---|
| Ninth Dimension portal | `http://SERVER-IP/` | Select an application |
| AI Assistant | `http://SERVER-IP:3000/` | Chat with your private AI assistant |
| Document Ingester — RAG | `http://SERVER-IP:8098/` | Upload documents and import public URLs |

The landing page links to the AI Assistant and Document Ingester.

If your server IP or hostname changes, update the links in `portal/index.html`.

The Knowledge Manager imports individual public HTTP(S) pages. It is not a full website crawler. File format support depends on the installed OPEA DataPrep version.

## 7. Verify the Deployment

### Check service status

```bash
./status.sh
```

Alternatively:

```bash
docker compose \
  --project-name private-rag \
  --env-file "$PWD/.env" \
  -f "$PWD/opea/compose.yaml" \
  -f "$PWD/opea/compose.vllm.override.yaml" \
  -f "$PWD/compose.app.yaml" \
  ps
```

### Check the landing page and favicon

```bash
curl -I http://127.0.0.1/
curl -I http://127.0.0.1/favicon.png
```

Expected response: `200 OK`.

If the landing page returns `403 Forbidden`, check that `portal/index.html` exists, is readable, and is mounted at `/usr/share/nginx/html` in the portal container.

### Check Knowledge Manager

```bash
curl -fsS http://127.0.0.1:8098/health
```

### Check DataPrep

```bash
curl -fsS http://127.0.0.1:6007/v1/health_check
```

### Check vLLM

```bash
curl -fsS http://127.0.0.1:8000/v1/models
```

The vLLM API is bound to localhost by default and should be tested from the server.

## 8. Ingest Knowledge Documents

### Using the UI

Open:

```text
http://SERVER-IP:8098/
```

Upload documents or import individual public HTTP(S) URLs.

### Using the DataPrep API

Example for a PDF on the server:

```bash
curl -X POST "http://127.0.0.1:6007/v1/dataprep/ingest" \
  -F "files=@/root/handbook.pdf"
```

Replace `/root/handbook.pdf` with the actual document path.

DataPrep processes the document and indexes its content for retrieval.

## 9. Persistent Data

A fresh deployment creates new named volumes. It does not automatically import documents, chat history, or model cache from another server.

| Volume | Purpose |
|---|---|
| `redis-data` | Redis/vector data, depending on the configured service |
| `open-webui-data` | Open WebUI users, settings, and chat history |
| `hf-cache` | Downloaded Hugging Face model files |

Confirm actual volume names and mounts before backup or migration:

```bash
docker volume ls
```

**Warning:** Never run `docker compose down -v` unless you intentionally want to delete named volumes.

Review `stop.sh` before production use to confirm it preserves persistent volumes.

## 10. Stop and Restart

Stop the platform:

```bash
./stop.sh
```

Start it again:

```bash
./deploy.sh
```

Before using these scripts on a new server, confirm that they use the same Compose files, project name, and `.env` file documented above.

## Configuration Files

| File or directory | Purpose |
|---|---|
| `opea/compose.yaml` | OPEA service definitions |
| `opea/compose.vllm.override.yaml` | vLLM deployment override |
| `compose.app.yaml` | Adapter, Open WebUI, Knowledge Manager, portal, and volumes |
| `adapter/` | OpenAI-compatible adapter |
| `knowledge-ui/` | Document upload and URL ingestion UI |
| `portal/` | Ninth Dimension landing page, logo, and favicon |
| `.env.example` | Non-secret configuration template |
| `deploy.sh` | Startup script |
| `status.sh` | Service status checks |
| `stop.sh` | Shutdown script |

## Production Security Checklist

- Configure HTTPS and a domain name where possible.
- Enable and verify authentication for both user-facing applications.
- Restrict public access to only the ports users need.
- Do not expose Redis, DataPrep, embeddings, reranking, or backend APIs directly to the internet unless specifically required and secured.
- Keep `.env` private and never commit secrets.
- Pin image versions or digests instead of relying on mutable tags such as `latest` or `main`.
- Back up persistent volumes and test restoration.
- Monitor GPU memory, disk space, container health, and model loading.
- Validate Compose changes with `docker compose config --quiet`.
- Test upgrades and restore procedures outside production first.
