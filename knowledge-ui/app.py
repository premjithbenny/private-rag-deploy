import asyncio
import ipaddress
import json
import os
import socket
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

app = FastAPI(title="Private RAG Knowledge Sources")

DATAPREP_URL = os.getenv(
    "DATAPREP_URL", "http://dataprep-redis-service:5000"
).rstrip("/")
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_FILES = 10

# These extensions are offered by the UI. The installed OPEA parser
# remains responsible for actually parsing each format.
ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls",
    ".csv", ".txt", ".md", ".html", ".htm", ".json",
}

PAGE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#082f75">
<title>Knowledge Manager | Ninth Dimension</title>
<style>
:root {
  --navy:#082f75; --blue:#0756c9; --blue-light:#eaf2ff;
  --orange:#f28c18; --orange-hover:#dc7610;
  --ink:#172b4d; --muted:#64748b; --line:#e2e8f0;
  --surface:#fff; --canvas:#f4f7fc; --green:#16794b;
}
*{box-sizing:border-box}
body{margin:0;background:var(--canvas);color:var(--ink);
  font:15px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
button,input,textarea{font:inherit}
.topbar{background:linear-gradient(105deg,#073b91,var(--navy) 65%,#0756a8);
  color:white;box-shadow:0 4px 18px #082f7524}
.top-inner{max-width:1180px;margin:auto;padding:18px 26px;
  display:flex;align-items:center;justify-content:space-between;gap:18px}
.brand{display:flex;align-items:center;gap:12px;min-width:0}
.brand-mark{width:43px;height:43px;border-radius:10px;background:var(--orange);
  display:grid;place-items:center;flex-shrink:0}
.brand-mark svg{width:26px;height:26px}
.brand-name{font-size:18px;font-weight:750;letter-spacing:.1px;line-height:1.3}
.brand-sub{font-size:10px;letter-spacing:1.6px;color:#d8e6ff;font-weight:650}
.top-status{display:flex;align-items:center;gap:8px;color:#e1edff;font-size:12px}
.dot{width:8px;height:8px;background:#5ee0a0;border-radius:50%;
  box-shadow:0 0 0 4px #5ee0a022}
main{max-width:1080px;margin:0 auto;padding:38px 24px 56px}
.eyebrow{font-size:11px;font-weight:800;letter-spacing:2px;color:var(--blue);
  text-transform:uppercase;margin-bottom:8px}
h1{font-size:clamp(28px,4vw,37px);line-height:1.17;letter-spacing:-1px;
  margin:0 0 12px;color:var(--ink)}
.intro{color:var(--muted);font-size:15px;max-width:660px;margin:0}
.hero{display:flex;justify-content:space-between;align-items:center;gap:24px;
  margin-bottom:28px}
.hero-icon{width:76px;height:76px;border-radius:22px;display:grid;place-items:center;
  background:linear-gradient(145deg,#eaf2ff,#fff);border:1px solid #dce8fb;
  flex-shrink:0}
.hero-icon svg{width:40px;height:40px;color:var(--blue)}
.section-label{font-size:11px;letter-spacing:1.5px;font-weight:800;
  color:var(--muted);text-transform:uppercase;margin:0 0 13px}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:stretch}
.card{background:var(--surface);border:1px solid var(--line);border-radius:17px;
  padding:25px;box-shadow:0 5px 22px #17365d08;min-width:0}
.card-head{display:flex;gap:13px;align-items:center;margin-bottom:8px}
.icon-box{width:45px;height:45px;border-radius:12px;display:grid;place-items:center;
  flex-shrink:0}
.icon-box svg{width:23px;height:23px}
.icon-blue{background:var(--blue-light);color:var(--blue)}
.icon-orange{background:#fff1df;color:var(--orange-hover)}
h2{font-size:19px;letter-spacing:-.3px;margin:0;font-weight:750}
.desc{font-size:13px;color:var(--muted);margin:0 0 22px}
.dropzone{position:relative;border:1.5px dashed #b7c9e5;border-radius:13px;
  padding:26px 15px;text-align:center;background:#f9fbff;
  transition:border-color .2s,background .2s}
.dropzone.drag{border-color:var(--orange);background:#fff8ee}
.dropzone input[type=file]{position:absolute;inset:0;width:100%;height:100%;
  opacity:0;cursor:pointer}
.upload-symbol{margin:0 auto 10px;width:48px;height:48px;border-radius:14px;
  background:#eaf2ff;color:var(--blue);display:grid;place-items:center}
.upload-symbol svg{width:25px;height:25px}
.drop-title{font-size:14px;font-weight:700;margin-bottom:3px}
.drop-hint{font-size:12px;color:var(--muted)}
.file-list{font-size:12px;color:var(--blue);margin-top:10px;
  overflow-wrap:anywhere;white-space:pre-line}
.field-label{display:block;font-size:13px;font-weight:700;margin-bottom:8px}
textarea{display:block;width:100%;min-height:155px;resize:vertical;padding:13px 14px;
  border:1px solid #d5deeb;border-radius:10px;background:#fcfdff;color:var(--ink);
  outline:none;transition:border-color .2s,box-shadow .2s}
textarea:focus,input:focus-visible,button:focus-visible{
  outline:3px solid #0756c926;outline-offset:2px}
textarea:focus{border-color:var(--blue);box-shadow:0 0 0 3px #0756c914}
textarea::placeholder{color:#9aa9bd}
.hint{font-size:12px;color:var(--muted);margin:10px 0 0;line-height:1.6}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:9px;
  border:0;border-radius:9px;padding:12px 17px;font-size:13px;font-weight:750;
  cursor:pointer;transition:background .2s,transform .2s}
.btn-primary{background:var(--orange);color:#fff;box-shadow:0 3px 9px #f28c182b}
.btn-primary:hover{background:var(--orange-hover);transform:translateY(-1px)}
.btn-secondary{background:#edf3ff;color:var(--blue)}
.btn-secondary:hover{background:#dce9ff}
.btn:disabled{opacity:.6;cursor:wait;transform:none}
.action-row{display:flex;align-items:center;justify-content:space-between;
  gap:12px;flex-wrap:wrap;margin-top:19px}
.checkrow{display:flex;align-items:flex-start;gap:9px;color:#475569;font-size:12px}
.checkrow input{accent-color:var(--blue);margin-top:3px}
.file-meta{font-size:12px;color:var(--muted);margin-top:14px}
.result-card{margin-top:22px}
.result-head{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.result-head h2{font-size:17px}
.result-icon{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;
  background:#edf3ff;color:var(--blue)}
#result{display:none;white-space:pre-wrap;overflow-wrap:anywhere;
  padding:15px;border-radius:10px;font-size:13px;line-height:1.65;
  max-height:360px;overflow:auto;background:#f1f5f9;color:#334155}
#result.success{display:block;background:#edfaf2;color:#166534;border:1px solid #c6efd4}
#result.error{display:block;background:#fff1f0;color:#9f2922;border:1px solid #ffd6d2}
#result.loading{display:block;background:#eef4ff;color:#17468b;border:1px solid #d5e4ff}
.footer{margin-top:30px;padding-top:20px;border-top:1px solid #e1e7f0;
  display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;
  color:#8290a5;font-size:11px}
.footer strong{color:var(--blue);font-weight:750}
@media(max-width:700px){
  .top-inner{padding:15px 18px}.top-status{font-size:0}.top-status .dot{font-size:initial}
  main{padding:28px 16px 38px}.hero{align-items:flex-start}.hero-icon{width:54px;height:54px;
    border-radius:15px}.hero-icon svg{width:29px;height:29px}
  .cards{grid-template-columns:1fr;gap:15px}.card{padding:20px}
  .brand-name{font-size:16px}.brand-sub{font-size:9px;letter-spacing:1px}
}
@media(prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
</style>
</head>
<body>
<header class="topbar">
  <div class="top-inner">
    <div class="brand">
      <div class="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 19V5l8-2 8 2v14l-8 2-8-2Z"/>
          <path d="M12 3v18M4 5l8 2 8-2M4 19l8-2 8 2"/>
        </svg>
      </div>
      <div>
        <div class="brand-name">Ninth Dimension</div>
        <div class="brand-sub">PRIVATE AI KNOWLEDGE PLATFORM</div>
      </div>
    </div>
    <div class="top-status"><span class="dot"></span> Private knowledge workspace</div>
  </div>
</header>

<main>
  <section class="hero">
    <div>
      <div class="eyebrow">AI Knowledge Infrastructure</div>
      <h1>Knowledge Manager</h1>
      <p class="intro">Bring your company's knowledge into one private AI workspace.
      Upload documents or import public web pages to make information searchable by your AI assistant.</p>
    </div>
    <div class="hero-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"
        stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 3 4.5 7v5c0 4.4 3.2 7.4 7.5 9 4.3-1.6 7.5-4.6 7.5-9V7L12 3Z"/>
        <path d="m9 12 2 2 4-4"/>
      </svg>
    </div>
  </section>

  <div class="section-label">Add to your knowledge base</div>
  <div class="cards">
    <section class="card">
      <div class="card-head">
        <div class="icon-box icon-blue" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
            stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/>
            <path d="M14 2v6h6M8 13h8M8 17h8"/>
          </svg>
        </div>
        <h2>Upload documents</h2>
      </div>
      <p class="desc">Add internal documents, reports, manuals and reference files.</p>
      <form id="upload">
        <div class="dropzone" id="dropzone">
          <input id="file-input" type="file" name="files" multiple required
            accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md,.html,.htm,.json"
            aria-label="Choose documents to upload">
          <div class="upload-symbol" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
              stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 16V4m-4 4 4-4 4 4"/>
              <path d="M20 16.5v3a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 19.5v-3"/>
            </svg>
          </div>
          <div class="drop-title">Drop files here or choose files</div>
          <div class="drop-hint">Up to 10 files · 25 MB per file</div>
          <div class="file-list" id="file-list" aria-live="polite"></div>
        </div>
        <p class="file-meta">PDF, Word, Excel, CSV, TXT, Markdown, HTML and JSON.
          Parser support depends on your installed OPEA version.</p>
        <div class="action-row">
          <label class="checkrow">
            <input type="checkbox" name="process_table">
            <span>Extract PDF tables<br><span style="color:#8290a5">May take longer</span></span>
          </label>
          <button class="btn btn-primary" type="submit">
            Upload and index <span aria-hidden="true">→</span>
          </button>
        </div>
      </form>
    </section>

    <section class="card">
      <div class="card-head">
        <div class="icon-box icon-orange" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
            stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10Z"/>
          </svg>
        </div>
        <h2>Import website URLs</h2>
      </div>
      <p class="desc">Add public web pages containing useful company or product information.</p>
      <form id="urls">
        <label class="field-label" for="url-list">Website page URLs</label>
        <textarea id="url-list" placeholder="https://example.com/handbook&#10;https://example.com/policies"></textarea>
        <p class="hint">Enter one public HTTP(S) URL per line, up to 10 URLs per request.
          Use pages you are authorized to index. Whole-site crawling is not included.</p>
        <div class="action-row">
          <span class="hint" style="margin:0">Public pages only</span>
          <button class="btn btn-primary" type="submit">
            Import web pages <span aria-hidden="true">→</span>
          </button>
        </div>
      </form>
    </section>
  </div>

  <section class="card result-card">
    <div class="result-head">
      <div class="result-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="21" height="21" fill="none"
          stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 11 12 14 22 4"/>
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
        </svg>
      </div>
      <div>
        <h2>Ingestion status</h2>
        <div class="hint" style="margin:2px 0 0">Feedback returned by the knowledge ingestion service</div>
      </div>
    </div>
    <div id="result" role="status" aria-live="polite"></div>
  </section>

  <footer class="footer">
    <span><strong>Ninth Dimension</strong> · Private AI Knowledge Platform</span>
    <span>Documents remain in your configured private RAG infrastructure</span>
  </footer>
</main>

<script>
const result = document.querySelector("#result");
const buttons = document.querySelectorAll("button");
const fileInput = document.querySelector("#file-input");
const fileList = document.querySelector("#file-list");
const dropzone = document.querySelector("#dropzone");

function showResult(kind, message) {
  result.className = kind;
  result.style.display = "block";
  result.textContent = message;
}
function displayFiles(files) {
  const list = Array.from(files);
  fileList.textContent = list.length
    ? list.map(f => f.name + " · " + (f.size / 1024 / 1024).toFixed(2) + " MB").join("\n")
    : "";
}
fileInput.addEventListener("change", () => displayFiles(fileInput.files));
["dragenter", "dragover"].forEach(eventName => dropzone.addEventListener(eventName, e => {
  e.preventDefault();
  dropzone.classList.add("drag");
}));
["dragleave", "drop"].forEach(eventName => dropzone.addEventListener(eventName, e => {
  e.preventDefault();
  dropzone.classList.remove("drag");
}));
dropzone.addEventListener("drop", e => {
  if (e.dataTransfer && e.dataTransfer.files.length) {
    fileInput.files = e.dataTransfer.files;
    displayFiles(fileInput.files);
  }
});

async function submitForm(url, body) {
  showResult("loading", "Processing your request…\nPlease wait while the documents or URLs are sent to DataPrep.");
  buttons.forEach(b => b.disabled = true);
  try {
    const r = await fetch(url, {method:"POST", body});
    const text = await r.text();
    let data;
    try { data = JSON.parse(text); } catch { data = {detail:text}; }
    showResult(r.ok ? "success" : "error",
      (r.ok ? "DataPrep response\n\n" : "Ingestion failed (HTTP " + r.status + ")\n\n") +
      JSON.stringify(data, null, 2));
  } catch (e) {
    showResult("error", "Request failed: " + e.message);
  } finally {
    buttons.forEach(b => b.disabled = false);
  }
}
document.querySelector("#upload").addEventListener("submit", async e => {
  e.preventDefault();
  const form = e.currentTarget;
  const selected = fileInput.files;
  if (!selected.length) return;
  if (selected.length > 10) {
    showResult("error", "Please select no more than 10 files per batch.");
    return;
  }
  const tooLarge = Array.from(selected).find(f => f.size > 25 * 1024 * 1024);
  if (tooLarge) {
    showResult("error", tooLarge.name + " exceeds the 25 MB per-file limit.");
    return;
  }
  const body = new FormData();
  for (const file of selected) body.append("files", file);
  body.append("process_table",
    form.querySelector('[name="process_table"]').checked ? "true" : "false");
  await submitForm("/api/upload", body);
});
document.querySelector("#urls").addEventListener("submit", async e => {
  e.preventDefault();
  const urls = document.querySelector("#url-list").value
    .split(/\n/).map(s => s.trim()).filter(Boolean);
  if (!urls.length) {
    showResult("error", "Enter at least one URL.");
    return;
  }
  if (urls.length > 10) {
    showResult("error", "Please enter no more than 10 URLs per request.");
    return;
  }
  await submitForm("/api/urls", new Blob([JSON.stringify({urls})],
    {type:"application/json"}));
});
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def home():
    return PAGE


@app.get("/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{DATAPREP_URL}/v1/health_check")
        return {"status": "ok" if r.is_success else "dataprep_unhealthy",
                "dataprep_status": r.status_code}
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"DataPrep unavailable: {exc}") from exc


async def send_to_dataprep(files=None, data=None):
    try:
        async with httpx.AsyncClient(timeout=600) as client:
            response = await client.post(
                f"{DATAPREP_URL}/v1/dataprep/ingest",
                files=files,
                data=data,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Cannot reach DataPrep: {exc}") from exc

    try:
        result = response.json()
    except ValueError:
        result = {"detail": response.text[:2000]}

    if response.is_error:
        raise HTTPException(response.status_code, result)
    return result


@app.post("/api/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    process_table: bool = Form(False),
):
    if not files or len(files) > MAX_FILES:
        raise HTTPException(400, f"Upload between 1 and {MAX_FILES} files.")

    payload = []
    try:
        for file in files:
            name = (file.filename or "").replace("\\", "/").split("/")[-1]
            ext = os.path.splitext(name)[1].lower()
            if not name or ext not in ALLOWED_EXTENSIONS:
                raise HTTPException(415, f"Unsupported file type: {name}")

            content = await file.read(MAX_FILE_BYTES + 1)
            if len(content) > MAX_FILE_BYTES:
                raise HTTPException(413, f"{name} exceeds 25 MB.")
            if not content:
                raise HTTPException(400, f"{name} is empty.")

            payload.append(
                ("files", (name, content, file.content_type or
                           "application/octet-stream"))
            )

        return await send_to_dataprep(
            files=payload,
            data={
                "chunk_size": "1500",
                "chunk_overlap": "100",
                "process_table": str(process_table).lower(),
                "table_strategy": "fast",
            },
        )
    finally:
        for file in files:
            await file.close()


def validate_public_url(value):
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(400, f"Invalid HTTP(S) URL: {value}")
    if parsed.username or parsed.password:
        raise HTTPException(400, "URLs containing credentials are not allowed.")
    if parsed.port and parsed.port not in (80, 443):
        raise HTTPException(400, "Only standard HTTP/HTTPS ports are allowed.")

    host = parsed.hostname
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(
            host, parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM
        )}
    except (OSError, ValueError) as exc:
        raise HTTPException(400, f"Cannot resolve URL host: {host}") from exc

    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise HTTPException(
                400, f"URLs resolving to non-public IP addresses are blocked: {host}"
            )
    return value


@app.post("/api/urls")
async def ingest_urls(payload: dict):
    urls = payload.get("urls")
    if not isinstance(urls, list) or not 1 <= len(urls) <= 10:
        raise HTTPException(400, "Provide between 1 and 10 URLs.")

    # Resolve/validate URLs concurrently to avoid blocking the event loop.
    validated = []
    for value in urls:
        if not isinstance(value, str) or len(value) > 2048:
            raise HTTPException(400, "Each URL must be a string under 2048 characters.")
        validated.append(await asyncio.to_thread(validate_public_url, value))

    return await send_to_dataprep(data={
        "link_list": json.dumps(validated),
        "chunk_size": "1500",
        "chunk_overlap": "100",
    })
