from contextlib import asynccontextmanager
import logging
import time
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.core.config import Config
from backend.models import (AuditRequest, AuditResponse, ChatRequest, ChatResponse, ComparisonResponse,
                            DocumentRecord, EvaluationResponse, RetrievalDebugCandidate,
                            RetrievalDebugRequest, RetrievalDebugResponse)
from backend.services.audit_service import AuditService
from backend.services.evaluation_service import EvaluationService
from backend.services.rag_service import RAGService
from backend.services.registry_service import RegistryService
from backend.services.search_service import SearchService
from backend.services.response_cache import TTLCache
from backend.admin import install_admin


logger = logging.getLogger("rag.api")


def services():
    """Build the application service graph once; tests may also use this factory directly."""
    registry = RegistryService()
    search = SearchService(registry=registry)
    rag = RAGService(search=search)
    audit = AuditService(registry, rag.search)
    evaluation = EvaluationService(audit)
    return registry, search, rag, audit, evaluation


@asynccontextmanager
async def lifespan(app: FastAPI):
    started = time.perf_counter()
    registry, search, rag, audit, evaluation = services()
    app.state.registry = registry
    app.state.search = search
    app.state.rag = rag
    app.state.audit = audit
    app.state.evaluation = evaluation
    app.state.chat_cache = TTLCache(
        max_entries=Config.CHAT_CACHE_MAX_ENTRIES,
        ttl_seconds=Config.CHAT_CACHE_TTL_SECONDS,
    )
    app.state.ready = True
    logger.info("service_graph_ready documents=%d chunks=%d startup_ms=%.1f",
                len(registry.records), len(search.chunks), (time.perf_counter() - started) * 1000)
    yield
    app.state.ready = False


app = FastAPI(title="IEEE SMCS Authority-aware RAG API", version="0.3.0", lifespan=lifespan)
install_admin(app)
app.add_middleware(CORSMiddleware, allow_origins=list(Config.CORS_ORIGINS),
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Request-ID"],
                   expose_headers=["X-Request-ID", "X-Cache", "Server-Timing"])
app.mount("/documents/corpus", StaticFiles(directory=Config.DATA_DIR / "corpus"), name="production-documents")


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))[:128]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed request_id=%s method=%s path=%s",
                         request_id, request.method, request.url.path)
        raise
    latency_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info("request_complete request_id=%s method=%s path=%s status=%d latency_ms=%.1f",
                request_id, request.method, request.url.path, response.status_code, latency_ms)
    return response


@app.get("/api/health")
def health(request: Request):
    """Backward-compatible readiness endpoint consumed by the frontend."""
    if not getattr(request.app.state, "ready", False):
        raise HTTPException(status_code=503, detail="Service graph is not ready")
    search = request.app.state.search
    return {"status": "ok", "default_mode": "deterministic", "development_mode": Config.DEVELOPMENT_MODE,
            "embedding": search.embeddings.configuration}


@app.get("/api/health/live")
def liveness():
    return {"status": "ok"}


@app.get("/api/health/ready")
def readiness(request: Request):
    if not getattr(request.app.state, "ready", False):
        raise HTTPException(status_code=503, detail="Service graph is not ready")
    registry, search = request.app.state.registry, request.app.state.search
    production = registry.production_documents()
    if not production or not search.chunks:
        raise HTTPException(status_code=503, detail="Production corpus is empty")
    return {"status": "ready", "documents": len(production), "chunks": len(search.chunks),
            "embedding": search.embeddings.configuration,
            "chat_cache_entries": len(request.app.state.chat_cache)}


@app.get("/api/documents", response_model=list[DocumentRecord])
def documents(request: Request):
    return request.app.state.registry.list_documents()


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest, http_request: Request, response: Response):
    cache_key = f"{request.mode}:{' '.join(request.question.casefold().split())}"
    cached = http_request.app.state.chat_cache.get(cache_key)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        response.headers["Server-Timing"] = "cache;desc=hit;dur=0"
        return cached
    started = time.perf_counter()
    result = http_request.app.state.rag.answer(request.question, request.mode)
    duration_ms = (time.perf_counter() - started) * 1000
    http_request.app.state.chat_cache.set(cache_key, result)
    response.headers["X-Cache"] = "MISS"
    response.headers["Server-Timing"] = f"rag;desc=retrieve-and-answer;dur={duration_ms:.1f}"
    return result


@app.post("/api/audit", response_model=AuditResponse)
def audit(request: AuditRequest, http_request: Request):
    try:
        return http_request.app.state.audit.audit(request.text, request.document_id, request.mode)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.post("/api/evaluation/run", response_model=EvaluationResponse)
def evaluation(request: Request):
    if not Config.ENABLE_EVALUATION_API:
        raise HTTPException(status_code=404, detail="Not found")
    return request.app.state.evaluation.evaluate()


@app.post("/api/evaluation/compare", response_model=ComparisonResponse)
def comparison(request: Request):
    if not Config.ENABLE_EVALUATION_API:
        raise HTTPException(status_code=404, detail="Not found")
    return request.app.state.evaluation.compare()


@app.post("/api/debug/retrieval", response_model=RetrievalDebugResponse, include_in_schema=Config.DEVELOPMENT_MODE)
def retrieval_debug(request: RetrievalDebugRequest, http_request: Request):
    if not Config.DEVELOPMENT_MODE:
        raise HTTPException(status_code=404, detail="Not found")
    rows = http_request.app.state.search.debug_search(request.query, k=10,
        document_ids=set(request.document_ids) if request.document_ids else None, mode=request.mode)
    candidates = [RetrievalDebugCandidate(
        chunk_id=item["chunk"].chunk_id, document_id=item["chunk"].document_id,
        document_title=item["chunk"].document_title, section=item["chunk"].section,
        page=item["chunk"].page, authority_level=item["chunk"].authority_level,
        approval_status=item["chunk"].approval_status, usage=item["chunk"].usage,
        candidate_clause=" ".join(item["chunk"].text.split())[:1200],
        lexical_score=round(item["lexical_score"], 6), vector_score=round(item["vector_score"], 6),
        bm25_score=round(item["bm25_score"], 6), rrf_score=round(item["rrf_score"], 6),
        hybrid_score=round(item["hybrid_score"], 6), reranking_score=round(item["reranking_score"], 6),
        included=item["included"], reason=item["reason"]) for item in rows]
    return RetrievalDebugResponse(query=request.query, candidates=candidates)


# Backwards-compatible route for the original frontend and scripts.
@app.post("/ask", response_model=ChatResponse)
def ask(request: dict, http_request: Request):
    question = request.get("question") or request.get("query")
    if not isinstance(question, str) or len(question.strip()) < 2:
        raise HTTPException(status_code=422, detail="question is required")
    return http_request.app.state.rag.answer(question, "deterministic")
