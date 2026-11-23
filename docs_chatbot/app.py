import hmac
import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, FastAPI, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse

from . import whatsapp as wa
from .config import Settings
from .embeddings import EmbeddingClient
from .handoff import HandoffStore
from .index import Index
from .ingest import SUPPORTED, chunk_directory, dir_fingerprint
from .llm import LLMClient, make_llm
from .memory import SessionStore
from .pipeline import ChatService
from .privacy import RedactingFilter, pseudonym
from .ratelimit import RateLimiter
from .retrieval import Retriever
from .schemas import ChatRequest, ChatResponse

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("docs_chatbot")
MAX_UPLOAD = 5 * 1024 * 1024


def make_embedder(s: Settings, http: httpx.AsyncClient | None = None) -> EmbeddingClient | None:
    if s.embeddings_provider == "none":
        return None
    base = s.embeddings_base_url or ("https://api.voyageai.com/v1" if s.embeddings_provider == "voyage"
                                     else "https://api.openai.com/v1")
    model = s.embeddings_model or ("voyage-3-lite" if s.embeddings_provider == "voyage"
                                   else "text-embedding-3-small")
    return EmbeddingClient(s.embeddings_provider, base, model, s.embeddings_api_key, http=http)


async def build_index(s: Settings, embedder: EmbeddingClient | None) -> Index:
    chunks = chunk_directory(s.kb_dir)
    emb = None
    meta = {"fingerprint": dir_fingerprint(s.kb_dir)}
    if embedder is not None and chunks:
        emb = await embedder.embed_documents([c.index_text for c in chunks])
        meta["embedding_model"] = embedder.model
    idx = Index(chunks, emb, meta)
    idx.save(s.index_dir)
    return idx


def create_app(settings: Settings | None = None, llm: LLMClient | None = None,
               http: httpx.AsyncClient | None = None) -> FastAPI:
    s = settings or Settings()
    logging.getLogger("docs_chatbot").addFilter(RedactingFilter())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        client = http or httpx.AsyncClient()
        embedder = make_embedder(s, client)
        index = None
        if (s.index_dir / "chunks.json").exists():
            index = Index.load(s.index_dir)
            if s.kb_dir.exists() and index.meta.get("fingerprint") != dir_fingerprint(s.kb_dir):
                index = None  # documents changed since the index was built
        if index is None:
            index = await build_index(s, embedder)
        app.state.http = client
        app.state.embedder = embedder
        app.state.retriever = Retriever(index, embedder)
        app.state.chat = ChatService(
            s, app.state.retriever, llm or make_llm(s, client), SessionStore(s.history_turns, s.session_ttl_seconds),
            HandoffStore(s.db_path), client)
        app.state.seen_wamids = {}
        yield
        if http is None:
            await client.aclose()

    app = FastAPI(title="AI Docs Chatbot", version="0.1.0", lifespan=lifespan)
    origins = [o.strip() for o in s.cors_origins.split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"])
    session_rl = RateLimiter(s.rate_limit_session_per_minute)
    ip_rl = RateLimiter(s.rate_limit_ip_per_minute)

    def client_ip(request: Request) -> str:
        if s.trust_proxy:
            fwd = request.headers.get("x-forwarded-for", "")
            if fwd:
                return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def limited(key_ip: str, key_session: str) -> int:
        """Return 0 when allowed, otherwise the Retry-After seconds."""
        ok, wait = ip_rl.check(key_ip)
        if not ok:
            return wait
        ok, wait = session_rl.check(key_session)
        return 0 if ok else wait

    @app.get("/health")
    async def health():
        idx = app.state.retriever.index
        return {"status": "ok", "llm": app.state.chat.llm.name, "documents": len(idx.docs),
                "chunks": len(idx.chunks), "embeddings": idx.embeddings is not None,
                "webhook_configured": bool(s.handoff_webhook_url),
                "whatsapp_configured": bool(s.whatsapp_app_secret and s.whatsapp_access_token)}

    @app.post("/chat", response_model=ChatResponse)
    async def chat(body: ChatRequest, request: Request, response: Response):
        sid = body.session_id or uuid.uuid4().hex
        wait = limited(client_ip(request), sid)
        if wait:
            raise HTTPException(429, "Too many messages. Please wait a moment.", headers={"Retry-After": str(wait)})
        return await app.state.chat.handle(sid, body.message, body.request_human, "web")

    @app.post("/ingest")
    async def ingest(files: list[UploadFile] = File(default=[]), x_admin_token: str | None = Header(default=None)):
        if not s.admin_token:
            raise HTTPException(403, "Ingest is disabled: set ADMIN_TOKEN")
        if not hmac.compare_digest(x_admin_token or "", s.admin_token):
            raise HTTPException(401, "Bad admin token")
        s.kb_dir.mkdir(parents=True, exist_ok=True)
        saved = []
        for f in files:
            name = Path(f.filename or "").name
            if Path(name).suffix.lower() not in SUPPORTED or name.startswith("."):
                raise HTTPException(400, f"Unsupported file type: {name or '(no name)'}")
            data = await f.read(MAX_UPLOAD + 1)
            if len(data) > MAX_UPLOAD:
                raise HTTPException(413, f"{name} is larger than 5 MB")
            (s.kb_dir / name).write_bytes(data)
            saved.append(name)
        try:
            index = await build_index(s, app.state.embedder)
        except Exception as e:  # a bad PDF should not leave the old index half replaced
            raise HTTPException(422, f"Could not index documents: {type(e).__name__}")
        app.state.retriever = Retriever(index, app.state.embedder)
        app.state.chat.retriever = app.state.retriever
        return {"saved": saved, "documents": len(index.docs), "chunks": len(index.chunks)}

    # ---- WhatsApp Cloud API ----
    @app.get("/whatsapp/webhook")
    async def wa_verify(request: Request):
        q = request.query_params
        token = s.whatsapp_verify_token
        if (q.get("hub.mode") == "subscribe" and token
                and hmac.compare_digest(q.get("hub.verify_token", ""), token)):
            return PlainTextResponse(q.get("hub.challenge", ""))
        raise HTTPException(403, "Verification failed")

    @app.post("/whatsapp/webhook")
    async def wa_incoming(request: Request, background: BackgroundTasks,
                          x_hub_signature_256: str | None = Header(default=None)):
        raw = await request.body()
        if not s.whatsapp_app_secret:
            raise HTTPException(503, "WhatsApp is not configured")
        if not wa.verify_signature(s.whatsapp_app_secret, raw, x_hub_signature_256):
            raise HTTPException(403, "Bad signature")
        try:
            payload = json.loads(raw)
        except ValueError:
            raise HTTPException(400, "Invalid JSON")
        for msg in wa.parse_messages(payload):
            if msg.id in app.state.seen_wamids:   # Meta retries deliveries
                continue
            app.state.seen_wamids[msg.id] = True
            if len(app.state.seen_wamids) > 5000:
                app.state.seen_wamids.pop(next(iter(app.state.seen_wamids)))
            background.add_task(_wa_reply, msg)
        return {"status": "received"}

    async def _wa_reply(msg: wa.Incoming) -> None:
        sid = f"wa:{msg.sender}"
        if msg.type != "text" or not msg.text.strip():
            body = "I can only read text messages. Please type your question."
        else:
            ok, _ = session_rl.check(sid)
            if not ok:
                return
            result = await app.state.chat.handle(sid, msg.text, channel="whatsapp")
            body = wa.format_reply(result.answer, result.citations)
        await wa.send_text(app.state.http, s.graph_base_url, s.whatsapp_phone_number_id,
                           s.whatsapp_access_token, msg.sender, body)

    # ---- demo assets ----
    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse("/demo")

    @app.get("/demo", include_in_schema=False)
    async def demo():
        return FileResponse(ROOT / "widget" / "demo.html")

    @app.get("/widget/chat.js", include_in_schema=False)
    async def widget_js():
        return FileResponse(ROOT / "widget" / "chat.js", media_type="application/javascript")

    return app


def app_factory() -> FastAPI:
    return create_app()
