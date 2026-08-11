from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.core.config import Config
from backend.models import (AuditRequest, AuditResponse, ChatRequest, ChatResponse,
                            DocumentRecord, EvaluationResponse, RetrievalDebugCandidate,
                            RetrievalDebugRequest, RetrievalDebugResponse)
from backend.services.audit_service import AuditService
from backend.services.evaluation_service import EvaluationService
from backend.services.rag_service import RAGService
from backend.services.registry_service import RegistryService
from backend.services.search_service import SearchService


app = FastAPI(title="IEEE SMCS Authority-aware RAG API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"],
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
app.mount("/documents/corpus", StaticFiles(directory=Config.DATA_DIR / "corpus"), name="production-documents")


def services():
    registry = RegistryService()
    rag = RAGService()
    audit = AuditService(registry, rag.search)
    return registry, rag, audit


@app.get("/api/health")
def health():
    return {"status": "ok", "mode": "deterministic_offline"}


@app.get("/api/documents", response_model=list[DocumentRecord])
def documents():
    return RegistryService().list_documents()


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    return RAGService().answer(request.question)


@app.post("/api/audit", response_model=AuditResponse)
def audit(request: AuditRequest):
    try:
        return AuditService().audit(request.text, request.document_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.post("/api/evaluation/run", response_model=EvaluationResponse)
def evaluation():
    return EvaluationService().evaluate()


@app.post("/api/debug/retrieval", response_model=RetrievalDebugResponse, include_in_schema=Config.DEVELOPMENT_MODE)
def retrieval_debug(request: RetrievalDebugRequest):
    if not Config.DEVELOPMENT_MODE:
        raise HTTPException(status_code=404, detail="Not found")
    rows = SearchService().debug_search(request.query, k=10,
        document_ids=set(request.document_ids) if request.document_ids else None)
    candidates = [RetrievalDebugCandidate(
        chunk_id=item["chunk"].chunk_id, document_id=item["chunk"].document_id,
        document_title=item["chunk"].document_title, section=item["chunk"].section,
        page=item["chunk"].page, authority_level=item["chunk"].authority_level,
        approval_status=item["chunk"].approval_status, usage=item["chunk"].usage,
        candidate_clause=" ".join(item["chunk"].text.split())[:1200],
        lexical_score=round(item["lexical_score"], 6), reranking_score=round(item["reranking_score"], 6),
        included=item["included"], reason=item["reason"]) for item in rows]
    return RetrievalDebugResponse(query=request.query, candidates=candidates)


# Backwards-compatible route for the original frontend and scripts.
@app.post("/ask", response_model=ChatResponse)
def ask(request: dict):
    question = request.get("question") or request.get("query")
    if not isinstance(question, str) or len(question.strip()) < 2:
        raise HTTPException(status_code=422, detail="question is required")
    return RAGService().answer(question)
