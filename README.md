# Ninth Dimension Private RAG Platform

A self-hosted private AI knowledge platform built with OPEA ChatQnA, vLLM, Redis, and Open WebUI. It includes a branded landing page where users can choose between the AI Assistant and the RAG Document Ingester.

## Components

| Component | Purpose | Access |
|---|---|---|
| vLLM | Serves Qwen2.5-7B-Instruct | `127.0.0.1:8000` |
| OPEA ChatQnA | RAG orchestration and question answering | Port `8888` |
| OPEA DataPrep | Document and URL ingestion | Port `6007` internally |
| Redis vector database | Stores indexed knowledge | Internal network |
| TEI embeddings | Embedding generation | Port `8090` |
| TEI reranking | Reranks retrieved passages | Port `8808` |
| Open WebUI | AI chat interface | Port `3000` |
| OpenAI-compatible adapter | Connects Open WebUI to OPEA ChatQnA | `127.0.0.1:8099` |
| Knowledge Manager | Uploads documents and imports public URLs | Port `8098` |
| Ninth Dimension portal | Landing page linking to the applications | Port `80` |
| Tavily Web Search | Provides internet search capabilities for current information | External API |

**Security:** Expose only the services users need. Keep Redis, DataPrep, embeddings, reranking, and backend APIs restricted to the server or a trusted network.

## Requirements

- Linux server with a supported NVIDIA GPU
- NVIDIA GPU driver and NVIDIA Container Toolkit
- Docker Engine and Docker Compose plugin
- Git, Python 3, and `curl`
- Sufficient disk space for container images and model weights
- Network access to download the required images and models
- Tavily API key for web search functionality
- Firewall rules configured for the intended application access

Verify the prerequisites:

```bash
nvidia-smi
docker --version
docker compose version
docker run --rm --gpus all ubuntu nvidia-smi
git --version
python3 --version
```

Resolve any GPU, Docker, or container runtime errors before continuing.

## 1. Clone the Repository

Create a working directory and clone the project:

```bash
mkdir -p "$HOME/projects"
cd "$HOME/projects"

git clone https://github.com/premjithbenny/private-rag-deploy.git

cd private-rag-deploy
```

If you already have a checkout, navigate to that repository instead.

## 2. Configure the Environment

The deployment script automatically creates `.env` from `.env.example` if `.env` does not exist. It also generates a persistent `WEBUI_SECRET_KEY` if one is missing or empty.

If you need to configure optional settings, create the environment file before deployment:

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Configure the required and optional environment variables.

### Tavily API Key — Required for Web Search

The platform uses Tavily to provide internet search capabilities to the AI assistant.

Add your Tavily API key to the `.env` file:

```env
TAVILY_API_KEY=your_tavily_api_key
```

Obtain an API key from:

https://tavily.com/

Replace `your_tavily_api_key` with your actual API key.

**Important:**
- A valid Tavily API key must be configured for web search to work.
- Keep the API key private.
- Never commit `.env` or API credentials to GitHub.
- Ensure the application container receives the `TAVILY_API_KEY` environment variable.
- If the key is changed, recreate or restart the relevant service so the updated environment variable is loaded.

### Other Environment Settings

You can also configure optional settings, such as `HF_TOKEN` for authenticated model downloads.

```env
HF_TOKEN=your_huggingface_token
```

The deployment script generates `WEBUI_SECRET_KEY` if no nonempty value is configured.

Important:
- Keep `.env` private.
- Never commit `.env`, API tokens, passwords, or other secrets to Git.
- Do not regenerate `WEBUI_SECRET_KEY` on every deployment. Changing it may invalidate existing sessions.
- Set `HF_TOKEN` only when your model or download configuration requires authentication.
- Do not overwrite an existing `.env` file with `.env.example` during routine deployments.

## 3. Deploy the Platform

From the repository root, run:

```bash
chmod +x deploy.sh status.sh stop.sh
./deploy.sh
```

The deployment script automatically:

1. Checks Docker, Docker Compose, Python, and `curl`.
2. Creates `.env` from `.env.example` if necessary.
3. Generates `WEBUI_SECRET_KEY` if no nonempty value is configured.
4. Validates the merged Docker Compose configuration.
5. Builds local images where required and starts the services.
6. Waits for the vLLM API and checks DataPrep health.
7. Displays the final service status.

Ensure that `TAVILY_API_KEY` is configured before deploying the web-search-enabled application.

The first deployment may take time while Docker downloads images and vLLM loads the model.

If deployment fails, review the reported error and inspect the service logs before retrying.

**Do not run `docker compose down -v` for routine troubleshooting.** This can delete persistent volumes and their data.

## 4. Access the Applications

Replace `SERVER-IP` with the IP address or hostname of your server.

| Application | URL | Purpose |
|---|---|---|
| Ninth Dimension portal | `http://SERVER-IP/` | Main landing page |
| AI Assistant | `http://SERVER-IP:3000/` | Chat with your AI assistant |
| Document Ingester — RAG | `http://SERVER-IP:8098/` | Upload documents and import public URLs |

The portal derives application links from the hostname and protocol used to open it. You normally do not need to hard-code the server IP in `portal/index.html`.

Ensure the required ports are published by Docker and allowed by your firewall. If port `8098` is bound only to localhost, the Knowledge Manager will be accessible only from the server until you configure an appropriate access method.

For production use, prefer HTTPS and a reverse proxy instead of exposing application ports directly.

The Knowledge Manager imports individual public HTTP(S) pages; it is not a full website crawler. Supported document formats depend on the installed OPEA DataPrep version.

## 5. Enable Web Search in Open WebUI

The platform supports internet search through Tavily, allowing the AI assistant to retrieve current information instead of relying exclusively on its locally hosted model.

Web search must be enabled in Open WebUI's administration settings.

### Configuration Steps

1. Make sure `TAVILY_API_KEY` is configured in the `.env` file.
2. Deploy or restart the application so the updated environment variables are available.
3. Log in to Open WebUI using an administrator account.
4. Open the **Admin Panel**.
5. Navigate to the **Settings** section.
6. Open the **Web Search** configuration.
7. Enable Web Search.
8. Select or configure Tavily as the search provider.
9. Verify that the Tavily API key is configured and saved.
10. Open the model configuration and enable Web Search for the RAG model.

### Using Web Search

Once enabled, users can use the RAG model in Open WebUI to ask questions requiring current internet information.

Example questions:

- What are the latest NVIDIA GPU announcements?
- What are the current AI infrastructure trends?
- Find the latest developments in Kubernetes.
- What are the latest government tenders related to AI infrastructure?

The assistant can use web search to retrieve current information and incorporate the results into its responses.

**Important:**
- Web Search must be enabled in the Open WebUI Admin Panel.
- Web Search must also be enabled for the RAG model being used.
- A valid Tavily API key is required.
- The server must have outbound internet connectivity.
- Local RAG document retrieval and internet web search are separate capabilities. Web Search does not replace the existing document ingestion and vector retrieval pipeline.

## 6. Verify the Deployment

### Check service status

Run:

```bash
./status.sh
```

Alternatively, inspect the Compose project:

```bash
docker compose \
  --project-name private-ai-knowledge-platform \
  --env-file "$PWD/.env" \
  -f "$PWD/opea/compose.yaml" \
  -f "$PWD/opea/compose.vllm.override.yaml" \
  -f "$PWD/compose.app.yaml" \
  ps
```

### Check the portal

```bash
curl -I http://127.0.0.1/
curl -I http://127.0.0.1/favicon.png
```

Expected response: `200 OK`.

If the portal returns `403 Forbidden`, check that `portal/index.html` exists, is readable, and is mounted correctly in the portal container.

### Check the Knowledge Manager

```bash
curl -fsS http://127.0.0.1:8098/health
echo
```

Expected response: a healthy status.

### Check DataPrep

```bash
curl -fsS http://127.0.0.1:6007/v1/health_check
echo
```

This endpoint is available only if the configured DataPrep service exposes it on the host.

### Check vLLM

```bash
curl -fsS http://127.0.0.1:8000/v1/models
echo
```

The vLLM API is bound to localhost by default and should be tested from the server.

### Verify Web Search

1. Open Open WebUI.
2. Select the configured RAG model.
3. Ask a question about a recent event or current information.
4. Verify that the web search functionality is triggered and results are incorporated into the answer.

If web search fails, check:

- `TAVILY_API_KEY` is present in `.env`.
- The application container receives the environment variable.
- The Tavily API key is valid.
- The server has outbound internet connectivity.
- Web Search is enabled in the Open WebUI Admin Panel.
- Web Search is enabled for the selected RAG model.

Successful health checks confirm that individual services are responding. They do not, by themselves, prove that document retrieval, internet search, and end-to-end RAG question answering work correctly.

## 7. Ingest Knowledge Documents

### Using the Document Ingester UI

Open:

```text
http://SERVER-IP:8098/
```

Upload supported documents or import individual public HTTP(S) URLs.

### Using the DataPrep API

For example, to submit a PDF located on the server:

```bash
curl -X POST "http://127.0.0.1:6007/v1/dataprep/ingest" \
  -F "files=@/root/handbook.pdf"
```

Replace `/root/handbook.pdf` with the actual path to your document.

DataPrep processes the document and indexes its content for retrieval. The exact API endpoint and supported formats depend on the deployed OPEA DataPrep version.

## 8. Persistent Data

The deployment uses Docker volumes to preserve application data. A fresh deployment does not automatically import documents, chat history, or model caches from another server.

| Volume | Purpose |
|---|---|
| `redis-data` | Redis/vector data, depending on the configured service |
| `open-webui-data` | Open WebUI users, settings, and chat history |
| `hf-cache` | Downloaded Hugging Face model files |

Inspect the actual volumes:

```bash
docker volume ls
```

Confirm the volume names and mount points in the Compose configuration before performing backups, migrations, or restoration.

**Warning:** Do not run `docker compose down -v` unless you intentionally want to delete the associated named volumes.

Back up persistent data regularly and test restoration procedures.

## 9. Stop and Restart

Stop the platform:

```bash
./stop.sh
```

Start it again:

```bash
./deploy.sh
```

The deployment script preserves an existing `.env` file and its configured `WEBUI_SECRET_KEY`. Do not delete or replace `.env` unless you intend to reconfigure the deployment.

Review `stop.sh` before production use to confirm that it preserves persistent volumes.

## Configuration Files

| File or directory | Purpose |
|---|---|
| `opea/compose.yaml` | OPEA service definitions |
| `opea/compose.vllm.override.yaml` | vLLM deployment override |
| `compose.app.yaml` | Adapter, Open WebUI, Knowledge Manager, portal, and volumes |
| `adapter/` | OpenAI-compatible adapter |
| `knowledge-ui/` | Document upload and URL ingestion UI |
| `portal/` | Landing page, logo, and favicon |
| `.env.example` | Non-secret configuration template |
| `.env` | Local environment configuration; never commit |
| `deploy.sh` | Configuration checks, startup, and readiness checks |
| `status.sh` | Service status checks |
| `stop.sh` | Shutdown script |

## Production Security Checklist

- Configure HTTPS and a domain name where possible.
- Enable and verify authentication for user-facing applications.
- Restrict public access to only the ports users need.
- Do not expose Redis, DataPrep, embeddings, reranking, or backend APIs directly to the internet unless specifically required and secured.
- Keep `.env` private and never commit secrets.
- Keep the Tavily API key private.
- Pin image versions or digests instead of relying on mutable tags such as `latest` or `main`.
- Back up persistent volumes and test restoration.
- Monitor GPU memory, disk space, container health, and model loading.
- Validate Compose changes with `docker compose config --quiet`.
- Test upgrades and restoration procedures before applying changes in production.
