import asyncio, ipaddress, json, os, re, socket, sqlite3, uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

DATAPREP_URL = os.getenv("DATAPREP_URL", "http://dataprep-redis-service:5000").rstrip("/")
INDEX_NAME = os.getenv("INDEX_NAME", "rag-redis")
DB_PATH = os.getenv("SOURCES_DB_PATH", "/data/knowledge_sources.db")
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_FILES = 10
MAX_DB_ROWS = int(os.getenv("MAX_DB_ROWS", "5000"))
MAX_DB_EXPORT_BYTES = int(os.getenv("MAX_DB_EXPORT_MB", "20")) * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".txt", ".md", ".html", ".htm", ".json"}
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]{0,127}$")
fernet_key = os.getenv("SOURCE_ENCRYPTION_KEY", "").strip()
if not fernet_key:
    raise RuntimeError("SOURCE_ENCRYPTION_KEY is required. Generate a Fernet key and add it to .env.")
try:
    FERNET = Fernet(fernet_key.encode())
except Exception as exc:
    raise RuntimeError("SOURCE_ENCRYPTION_KEY is invalid. Generate a Fernet key and keep it stable across restarts.") from exc

sync_locks: dict[str, asyncio.Lock] = {}
scheduler_task: asyncio.Task | None = None


def now_iso(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
def db_conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db_conn() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS sources (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, db_type TEXT NOT NULL,
            host TEXT NOT NULL, port INTEGER NOT NULL, database_name TEXT NOT NULL,
            username TEXT NOT NULL, password_enc TEXT NOT NULL, object_name TEXT NOT NULL,
            primary_key TEXT, tls INTEGER NOT NULL DEFAULT 1, interval_minutes INTEGER NOT NULL DEFAULT 60,
            enabled INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'pending',
            last_sync TEXT, next_sync TEXT, last_error TEXT, records_count INTEGER NOT NULL DEFAULT 0,
            current_file TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )""")

def source_public(row):
    d = dict(row)
    d.pop("password_enc", None)
    d["tls"] = bool(d["tls"]); d["enabled"] = bool(d["enabled"])
    return d

def get_source(source_id):
    with db_conn() as con: row = con.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
    if not row: raise HTTPException(404, "Source not found.")
    return dict(row)

def validate_ident(value, label):
    if not value or not IDENT.fullmatch(value):
        raise HTTPException(400, f"{label} must start with a letter/underscore and contain only letters, numbers, underscore or $.")
    return value

def quote_ident(value, db_type):
    validate_ident(value, "Table/collection/column name")
    return f'`{value}`' if db_type == "mysql" else f'"{value}"'

def safe_value(v):
    if v is None or isinstance(v, (str, int, float, bool)): return v
    if hasattr(v, "isoformat"): return v.isoformat()
    if isinstance(v, bytes): return v.decode("utf-8", "replace")
    if isinstance(v, dict): return {str(k): safe_value(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)): return [safe_value(x) for x in v]
    try: return str(v)
    except Exception: return repr(v)

def fetch_rows(source):
    typ, host, port = source["db_type"], source["host"], int(source["port"])
    database, username = source["database_name"], source["username"]
    password = FERNET.decrypt(source["password_enc"].encode()).decode()
    obj = validate_ident(source["object_name"], "Table/collection name")
    tls = bool(source["tls"])
    if typ == "postgres":
        import psycopg
        from psycopg import sql
        conn = psycopg.connect(host=host, port=port, dbname=database, user=username, password=password,
                               connect_timeout=10, sslmode="require" if tls else "prefer", options="-c statement_timeout=60000")
        try:
            with conn.cursor() as cur:
                cur.execute(sql.SQL("SELECT * FROM {} LIMIT %s").format(sql.Identifier(obj)), (MAX_DB_ROWS + 1,))
                cols = [d.name for d in cur.description]
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        finally: conn.close()
    elif typ == "mysql":
        import pymysql
        conn = pymysql.connect(host=host, port=port, database=database, user=username, password=password,
                               connect_timeout=10, read_timeout=60, write_timeout=10,
                               ssl={"check_hostname": True} if tls else None, cursorclass=pymysql.cursors.DictCursor,
                               charset="utf8mb4")
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {quote_ident(obj, 'mysql')} LIMIT %s", (MAX_DB_ROWS + 1,))
                rows = list(cur.fetchall())
        finally: conn.close()
    elif typ == "mongodb":
        from pymongo import MongoClient
        uri = f"mongodb://{__import__('urllib.parse', fromlist=['quote_plus']).quote_plus(username)}:{__import__('urllib.parse', fromlist=['quote_plus']).quote_plus(password)}@{host}:{port}/{database}?authSource={database}&connectTimeoutMS=10000&serverSelectionTimeoutMS=10000"
        client = MongoClient(uri, tls=tls, tlsAllowInvalidCertificates=False, appname="PrivateRAGKnowledgeManager")
        try:
            client.admin.command("ping")
            rows = list(client[database][obj].find({}, limit=MAX_DB_ROWS + 1))
        finally: client.close()
        rows = [{k: safe_value(v) for k, v in row.items()} for row in rows]
    else: raise HTTPException(400, "Unsupported database type.")
    if len(rows) > MAX_DB_ROWS:
        raise HTTPException(413, f"Source returned more than {MAX_DB_ROWS} records. Reduce the table/collection size before syncing.")
    return rows

def test_connection(source):
    rows = fetch_rows(source)
    return len(rows)

async def dataprep_request(method, path, **kwargs):
    try:
        async with httpx.AsyncClient(timeout=600) as client:
            r = await client.request(method, f"{DATAPREP_URL}{path}", **kwargs)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"DataPrep unavailable: {type(exc).__name__}") from exc
    try: data = r.json()
    except ValueError: data = {"detail": r.text[:1500]}
    if r.is_error: raise HTTPException(r.status_code, data)
    return data

async def send_to_dataprep(files=None, data=None):
    return await dataprep_request("POST", "/v1/dataprep/ingest", files=files, data=data)

async def delete_dataprep_file(filename):
    # DataPrep's delete API expects file_path and index_name as embedded JSON fields.
    try:
        await dataprep_request("POST", "/v1/dataprep/delete", json={"file_path": filename, "index_name": INDEX_NAME})
    except HTTPException as exc:
        # A missing previous file is safe during cleanup; other errors are surfaced.
        detail = str(exc.detail).lower()
        if exc.status_code != 404 and "not found" not in detail and "does not exists" not in detail:
            raise

async def sync_source(source_id, force=False):
    lock = sync_locks.setdefault(source_id, asyncio.Lock())
    if lock.locked(): return {"status": "already_running", "source_id": source_id}
    async with lock:
        source = get_source(source_id)
        if not source["enabled"] and not force:
            return {"status": "paused", "source_id": source_id}
        with db_conn() as con:
            con.execute("UPDATE sources SET status='syncing',last_error=NULL,updated_at=? WHERE id=?", (now_iso(), source_id))
        try:
            rows = await asyncio.to_thread(fetch_rows, source)
            run_id = uuid.uuid4().hex[:12]
            filename = f"dbsource_{source_id}_{run_id}.json"
            document = {
                "source_name": source["name"], "database_type": source["db_type"],
                "database": source["database_name"], "table_or_collection": source["object_name"],
                "synced_at": now_iso(), "record_count": len(rows),
                "records": rows,
            }
            content = json.dumps(document, ensure_ascii=False, default=safe_value, separators=(",", ":")).encode("utf-8")
            if len(content) > MAX_DB_EXPORT_BYTES:
                raise HTTPException(413, f"Export exceeds {MAX_DB_EXPORT_BYTES // (1024*1024)} MB. Reduce the selected table/collection size.")
            result = await send_to_dataprep(
                files=[("files", (filename, content, "application/json"))],
                data={"chunk_size":"1500", "chunk_overlap":"100", "process_table":"false", "table_strategy":"fast", "index_name":INDEX_NAME},
            )
            old_file = source.get("current_file")
            # Index the new export successfully before removing the previous version.
            if old_file and old_file != filename:
                await delete_dataprep_file(old_file)
            next_sync = (datetime.now(timezone.utc) + timedelta(minutes=int(source["interval_minutes"]))).isoformat(timespec="seconds")
            with db_conn() as con:
                con.execute("UPDATE sources SET status='healthy',last_sync=?,next_sync=?,last_error=NULL,records_count=?,current_file=?,updated_at=? WHERE id=?",
                            (now_iso(), next_sync, len(rows), filename, now_iso(), source_id))
            return {"status":"ok", "source_id":source_id, "records_count":len(rows), "dataprep":result}
        except Exception as exc:
            message = exc.detail if isinstance(exc, HTTPException) else f"{type(exc).__name__}: {exc}"
            message = str(message)[:1500]
            with db_conn() as con:
                con.execute("UPDATE sources SET status='error',last_error=?,next_sync=?,updated_at=? WHERE id=?",
                            (message, (datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(timespec="seconds"), now_iso(), source_id))
            raise

async def scheduler_loop():
    while True:
        try:
            with db_conn() as con:
                rows = con.execute("SELECT id,next_sync FROM sources WHERE enabled=1").fetchall()
            now = datetime.now(timezone.utc)
            for row in rows:
                due = True
                if row["next_sync"]:
                    try: due = datetime.fromisoformat(row["next_sync"]) <= now
                    except ValueError: due = True
                if due:
                    try: await sync_source(row["id"])
                    except Exception: pass
        except Exception:
            pass
        await asyncio.sleep(30)

@asynccontextmanager
async def lifespan(app):
    global scheduler_task
    init_db()
    scheduler_task = asyncio.create_task(scheduler_loop())
    try: yield
    finally:
        if scheduler_task:
            scheduler_task.cancel()
            try: await scheduler_task
            except asyncio.CancelledError: pass

app = FastAPI(title="Private RAG Knowledge Sources", lifespan=lifespan)

PAGE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Knowledge Manager | Ninth Dimension</title><style>
:root{--navy:#082f75;--blue:#0756c9;--orange:#e47d16;--ink:#172b4d;--muted:#64748b;--line:#e2e8f0;--canvas:#f4f7fc}*{box-sizing:border-box}body{margin:0;background:var(--canvas);color:var(--ink);font:15px/1.5 Inter,system-ui,sans-serif}header{background:linear-gradient(105deg,#073b91,var(--navy));color:white;padding:18px max(20px,calc((100% - 1100px)/2));font-weight:800}header small{display:block;font-size:10px;letter-spacing:1.6px;color:#d8e6ff}main{max-width:1100px;margin:auto;padding:32px 20px}.intro{color:var(--muted);max-width:760px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.card{background:white;border:1px solid var(--line);border-radius:15px;padding:22px;margin:18px 0;min-width:0}.card h2{margin:0 0 6px;font-size:19px}.desc,.hint{color:var(--muted);font-size:13px}.field{display:grid;gap:6px;margin:12px 0}.field label{font-size:13px;font-weight:700}.field input,.field select,.field textarea{width:100%;border:1px solid #ccd7e6;border-radius:8px;padding:10px;background:#fff;color:var(--ink);font:inherit}.fields3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}.btn{border:0;border-radius:8px;background:var(--orange);color:white;padding:11px 15px;font-weight:750;cursor:pointer}.btn.secondary{background:#eaf2ff;color:var(--blue)}.btn.danger{background:#fff0ef;color:#a52822}.btn:disabled{opacity:.6}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.status{font-size:12px;border-radius:99px;padding:4px 9px;background:#edf2f7;color:#475569}.status.healthy{background:#e7f8ed;color:#166534}.status.error{background:#fff0ef;color:#a52822}.status.syncing{background:#eaf2ff;color:#17468b}.source{border:1px solid var(--line);border-radius:11px;padding:15px;margin-top:12px;background:#fff}.source-top{display:flex;justify-content:space-between;gap:10px;align-items:start}.source p{margin:6px 0;color:var(--muted);font-size:12px;overflow-wrap:anywhere}.actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}.actions .btn{font-size:12px;padding:8px 10px}#result{white-space:pre-wrap;overflow-wrap:anywhere;padding:12px;border-radius:8px;background:#f1f5f9;display:none;font-size:13px}#result.success{display:block;background:#edfaf2;color:#166534}#result.error{display:block;background:#fff1f0;color:#9f2922}#result.loading{display:block;background:#eef4ff;color:#17468b}.full{grid-column:1/-1}footer{color:#8290a5;font-size:11px;border-top:1px solid var(--line);padding-top:18px;margin-top:25px}@media(max-width:760px){.grid,.fields3{grid-template-columns:1fr}.full{grid-column:auto}main{padding:20px 13px}.card{padding:16px}}
</style></head><body><header>Ninth Dimension <small>PRIVATE AI KNOWLEDGE PLATFORM</small></header><main><h1>Knowledge Manager</h1><p class="intro">Upload internal documents, import public website pages, or connect PostgreSQL, MySQL and MongoDB sources to your private RAG knowledge base. Database sources sync automatically every 60 minutes by default.</p>
<div class="grid"><section class="card"><h2>Upload documents</h2><p class="desc">Existing document ingestion is preserved.</p><form id="upload"><div class="field"><label for="files">Files (up to 10; 25 MB each)</label><input id="files" type="file" multiple required accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md,.html,.htm,.json"></div><label><input id="process_table" type="checkbox"> Extract PDF tables</label><p><button class="btn">Upload and index</button></p></form></section>
<section class="card"><h2>Import website URLs</h2><p class="desc">One public HTTP(S) URL per line, up to 10.</p><form id="urls"><div class="field"><label for="url_list">Website page URLs</label><textarea id="url_list" rows="5" placeholder="https://example.com/handbook" required></textarea></div><button class="btn">Import web pages</button></form></section>
<section class="card full"><h2>Connect a database</h2><p class="desc">Use a read-only account and select one table or collection per source. Database sync exports up to the configured row/size limits to DataPrep.</p><form id="source-form"><div class="fields3"><div class="field"><label>Source name</label><input name="name" required maxlength="100" placeholder="CRM customers"></div><div class="field"><label>Database type</label><select name="db_type" id="db_type"><option value="postgres">PostgreSQL</option><option value="mysql">MySQL</option><option value="mongodb">MongoDB</option></select></div><div class="field"><label>Sync interval (minutes)</label><input name="interval_minutes" type="number" min="15" max="1440" value="60" required></div></div><div class="fields3"><div class="field"><label>Host</label><input name="host" required placeholder="db.internal.example"></div><div class="field"><label>Port</label><input name="port" type="number" required value="5432"></div><div class="field"><label>Database name</label><input name="database_name" required></div></div><div class="fields3"><div class="field"><label>Username</label><input name="username" required autocomplete="off"></div><div class="field"><label>Password</label><input name="password" type="password" required autocomplete="new-password"></div><div class="field"><label id="object-label">Table name</label><input name="object_name" required placeholder="customers"></div></div><div class="fields3"><div class="field"><label>Primary key (optional, informational)</label><input name="primary_key" placeholder="id"></div><div class="field"><label>TLS</label><select name="tls"><option value="true" selected>Require / enable TLS</option><option value="false">Disable TLS (trusted network only)</option></select></div><div class="field"><label>&nbsp;</label><button class="btn" type="submit">Test, save and sync</button></div></div><p class="hint">Password is encrypted before being stored by this application. The source is tested and its first sync starts immediately. MongoDB expects host, port, database, username, password and collection separately.</p></form></section>
<section class="card full"><div class="row" style="justify-content:space-between"><div><h2>Connected database sources</h2><p class="desc">Last sync, schedule, row count and errors.</p></div><button class="btn secondary" id="refresh" type="button">Refresh status</button></div><div id="sources"><p class="hint">Loading sources…</p></div></section>
<section class="card full"><h2>Ingestion status</h2><div id="result" role="status" aria-live="polite"></div></section></div><footer><b>Ninth Dimension</b> · Private AI Knowledge Platform · Database credentials never appear in source-list API responses.</footer></main>
<script>
const $=s=>document.querySelector(s), result=$('#result');
function show(kind,msg){result.className=kind;result.textContent=msg;result.style.display='block'}
async function req(url,opts={}){const r=await fetch(url,opts);let d;try{d=await r.json()}catch{d={detail:await r.text()}}if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:JSON.stringify(d.detail||d));return d}
async function action(url,method='POST'){try{show('loading','Working…');const d=await req(url,{method});show('success',JSON.stringify(d,null,2));await loadSources()}catch(e){show('error',e.message)}}
$('#db_type').addEventListener('change',e=>{const p={postgres:5432,mysql:3306,mongodb:27017};$('input[name=port]').value=p[e.target.value];$('#object-label').textContent=e.target.value==='mongodb'?'Collection name':'Table name'});
$('#upload').addEventListener('submit',async e=>{e.preventDefault();const fs=$('#files').files;if(!fs.length)return; if(fs.length>10)return show('error','Select no more than 10 files.');for(const f of fs)if(f.size>25*1024*1024)return show('error',f.name+' exceeds 25 MB.');const b=new FormData();for(const f of fs)b.append('files',f);b.append('process_table',$('#process_table').checked?'true':'false');try{show('loading','Uploading and indexing…');show('success',JSON.stringify(await req('/api/upload',{method:'POST',body:b}),null,2));}catch(e){show('error',e.message)}});
$('#urls').addEventListener('submit',async e=>{e.preventDefault();const urls=$('#url_list').value.split(/\n/).map(x=>x.trim()).filter(Boolean);try{show('loading','Importing web pages…');show('success',JSON.stringify(await req('/api/urls',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({urls})}),null,2));}catch(e){show('error',e.message)}});
$('#source-form').addEventListener('submit',async e=>{e.preventDefault();const form=e.currentTarget;const b=Object.fromEntries(new FormData(form));b.port=Number(b.port);b.interval_minutes=Number(b.interval_minutes);b.tls=b.tls==='true';try{show('loading','Testing database connection, saving source and running first sync…');const d=await req('/api/sources',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});show('success',JSON.stringify(d,null,2));form.reset();$('#source-form [name=interval_minutes]').value=60;$('#db_type').dispatchEvent(new Event('change'));await loadSources()}catch(e){show('error',e.message)}});
async function loadSources(){try{const d=await req('/api/sources');const root=$('#sources');if(!d.sources.length){root.innerHTML='<p class="hint">No database sources connected yet.</p>';return}root.innerHTML='';for(const s of d.sources){const el=document.createElement('div');el.className='source';const top=document.createElement('div');top.className='source-top';const left=document.createElement('div');const title=document.createElement('b');title.textContent=s.name+' · '+s.db_type.toUpperCase();const meta=document.createElement('p');meta.textContent=s.host+':'+s.port+' / '+s.database_name+' / '+s.object_name+' · '+s.records_count+' records';left.append(title,meta);const badge=document.createElement('span');badge.className='status '+(s.status==='healthy'?'healthy':s.status==='error'?'error':s.status==='syncing'?'syncing':'');badge.textContent=s.enabled?s.status:'paused';top.append(left,badge);el.append(top);const info=document.createElement('p');info.textContent='Interval: '+s.interval_minutes+' min · Last sync: '+(s.last_sync||'Never')+' · Next sync: '+(s.next_sync||'Not scheduled');el.append(info);if(s.last_error){const err=document.createElement('p');err.style.color='#a52822';err.textContent='Last error: '+s.last_error;el.append(err)}const acts=document.createElement('div');acts.className='actions';function btn(label,cls,fn){const b=document.createElement('button');b.className='btn '+cls;b.textContent=label;b.onclick=fn;acts.append(b)}btn('Sync now','',()=>action('/api/sources/'+s.id+'/sync'));btn(s.enabled?'Pause':'Resume','secondary',()=>action('/api/sources/'+s.id+'/'+(s.enabled?'pause':'resume')));btn('Delete source','danger',()=>{if(confirm('Delete source configuration and its indexed documents?'))action('/api/sources/'+s.id,'DELETE')});el.append(acts);root.append(el)}}catch(e){$('#sources').textContent='Could not load sources: '+e.message}}
$('#refresh').addEventListener('click',loadSources);loadSources();setInterval(loadSources,30000);
</script></body></html>'''

@app.get("/", response_class=HTMLResponse)
async def home(): return PAGE

@app.get("/health")
async def health():
    try:
        async with httpx.AsyncClient(timeout=5) as client: r = await client.get(f"{DATAPREP_URL}/v1/health_check")
        return {"status":"ok" if r.is_success else "dataprep_unhealthy", "dataprep_status":r.status_code}
    except httpx.HTTPError as exc: raise HTTPException(502, f"DataPrep unavailable: {type(exc).__name__}") from exc

@app.post("/api/upload")
async def upload_files(files: list[UploadFile] = File(...), process_table: bool = Form(False)):
    if not files or len(files)>MAX_FILES: raise HTTPException(400, f"Upload between 1 and {MAX_FILES} files.")
    payload=[]
    try:
        for file in files:
            name=(file.filename or "").replace("\\","/").split("/")[-1]; ext=os.path.splitext(name)[1].lower()
            if not name or ext not in ALLOWED_EXTENSIONS: raise HTTPException(415, f"Unsupported file type: {name}")
            content=await file.read(MAX_FILE_BYTES+1)
            if len(content)>MAX_FILE_BYTES: raise HTTPException(413, f"{name} exceeds 25 MB.")
            if not content: raise HTTPException(400, f"{name} is empty.")
            payload.append(("files",(name,content,file.content_type or "application/octet-stream")))
        return await send_to_dataprep(files=payload,data={"chunk_size":"1500","chunk_overlap":"100","process_table":str(process_table).lower(),"table_strategy":"fast","index_name":INDEX_NAME})
    finally:
        for file in files: await file.close()

def validate_public_url(value):
    parsed=urlparse(value)
    if parsed.scheme not in ("http","https") or not parsed.hostname: raise HTTPException(400,f"Invalid HTTP(S) URL: {value}")
    if parsed.username or parsed.password: raise HTTPException(400,"URLs containing credentials are not allowed.")
    if parsed.port and parsed.port not in (80,443): raise HTTPException(400,"Only standard HTTP/HTTPS ports are allowed.")
    try: addresses={x[4][0] for x in socket.getaddrinfo(parsed.hostname,parsed.port or (443 if parsed.scheme=="https" else 80),type=socket.SOCK_STREAM)}
    except (OSError,ValueError) as exc: raise HTTPException(400,f"Cannot resolve URL host: {parsed.hostname}") from exc
    for address in addresses:
        if not ipaddress.ip_address(address).is_global: raise HTTPException(400,f"URLs resolving to non-public IP addresses are blocked: {parsed.hostname}")
    return value

@app.post("/api/urls")
async def ingest_urls(payload: dict):
    urls=payload.get("urls")
    if not isinstance(urls,list) or not 1<=len(urls)<=10: raise HTTPException(400,"Provide between 1 and 10 URLs.")
    valid=[]
    for value in urls:
        if not isinstance(value,str) or len(value)>2048: raise HTTPException(400,"Each URL must be a string under 2048 characters.")
        valid.append(await asyncio.to_thread(validate_public_url,value))
    return await send_to_dataprep(data={"link_list":json.dumps(valid),"chunk_size":"1500","chunk_overlap":"100","index_name":INDEX_NAME})

class SourceInput(BaseModel):
    name: str = Field(min_length=1,max_length=100)
    db_type: str
    host: str = Field(min_length=1,max_length=253)
    port: int = Field(ge=1,le=65535)
    database_name: str = Field(min_length=1,max_length=128)
    username: str = Field(min_length=1,max_length=128)
    password: str = Field(min_length=1,max_length=2048)
    object_name: str = Field(min_length=1,max_length=128)
    primary_key: str | None = Field(default=None,max_length=128)
    tls: bool = True
    interval_minutes: int = Field(default=60,ge=15,le=1440)

@app.get("/api/sources")
async def list_sources():
    with db_conn() as con: rows=con.execute("SELECT * FROM sources ORDER BY created_at DESC").fetchall()
    return {"sources":[source_public(r) for r in rows]}

@app.post("/api/sources")
async def create_source(payload: SourceInput):
    typ=payload.db_type.lower()
    if typ not in ("postgres","mysql","mongodb"): raise HTTPException(400,"db_type must be postgres, mysql or mongodb.")
    if not payload.host.strip() or any(ch in payload.host for ch in " /\\@\n\r"): raise HTTPException(400,"Enter a hostname or IP address, not a URL.")
    obj=validate_ident(payload.object_name, "Table/collection name")
    if payload.primary_key: validate_ident(payload.primary_key,"Primary key")
    if typ=="postgres" and payload.port==5432: pass
    source_id=uuid.uuid4().hex
    source={"id":source_id,"name":payload.name.strip(),"db_type":typ,"host":payload.host.strip(),"port":payload.port,
            "database_name":payload.database_name.strip(),"username":payload.username,"password_enc":FERNET.encrypt(payload.password.encode()).decode(),
            "object_name":obj,"primary_key":payload.primary_key,"tls":int(payload.tls),"interval_minutes":payload.interval_minutes,"enabled":1,
            "status":"pending","last_sync":None,"next_sync":None,"last_error":None,"records_count":0,"current_file":None,"created_at":now_iso(),"updated_at":now_iso()}
    try: count=await asyncio.to_thread(test_connection,source)
    except HTTPException: raise
    except Exception as exc:
        # Avoid returning exception strings that may contain connection details or credentials.
        raise HTTPException(400,f"Database connection/test failed ({type(exc).__name__}). Check host, port, credentials, TLS and object name.") from exc
    with db_conn() as con:
        con.execute("""INSERT INTO sources(id,name,db_type,host,port,database_name,username,password_enc,object_name,primary_key,tls,interval_minutes,enabled,status,last_sync,next_sync,last_error,records_count,current_file,created_at,updated_at)
        VALUES(:id,:name,:db_type,:host,:port,:database_name,:username,:password_enc,:object_name,:primary_key,:tls,:interval_minutes,:enabled,:status,:last_sync,:next_sync,:last_error,:records_count,:current_file,:created_at,:updated_at)""",source)
    try: sync_result=await sync_source(source_id,force=True)
    except Exception as exc:
        return {"source":source_public(get_source(source_id)),"test_records":count,"sync":"failed","detail":str(exc.detail if isinstance(exc,HTTPException) else type(exc).__name__)}
    return {"source":source_public(get_source(source_id)),"test_records":count,"sync":sync_result}

@app.post("/api/sources/{source_id}/sync")
async def sync_now(source_id: str):
    get_source(source_id)
    try: return await sync_source(source_id,force=True)
    except HTTPException: raise
    except Exception as exc: raise HTTPException(500,f"Sync failed ({type(exc).__name__}). See source status for details.") from exc

@app.post("/api/sources/{source_id}/pause")
async def pause_source(source_id: str):
    get_source(source_id)
    with db_conn() as con: con.execute("UPDATE sources SET enabled=0,status='paused',next_sync=NULL,updated_at=? WHERE id=?",(now_iso(),source_id))
    return {"status":"paused","source_id":source_id}

@app.post("/api/sources/{source_id}/resume")
async def resume_source(source_id: str):
    get_source(source_id)
    with db_conn() as con: con.execute("UPDATE sources SET enabled=1,status='pending',next_sync=?,updated_at=? WHERE id=?",(now_iso(),now_iso(),source_id))
    return {"status":"resumed","source_id":source_id}

@app.delete("/api/sources/{source_id}")
async def delete_source(source_id: str):
    source=get_source(source_id)
    if source.get("current_file"):
        await delete_dataprep_file(source["current_file"])
    with db_conn() as con: con.execute("DELETE FROM sources WHERE id=?",(source_id,))
    return {"status":"deleted","source_id":source_id,"indexed_file_removed":bool(source.get("current_file"))}
