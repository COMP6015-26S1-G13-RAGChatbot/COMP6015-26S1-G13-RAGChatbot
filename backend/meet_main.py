"""Web API for the selected team engine and administrator lifecycle."""
from contextlib import asynccontextmanager
import importlib
import json
import os
from pathlib import Path
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.admin import install_admin, storage
from backend.services.meet_admin_adapter import install_meet_lifecycle


def check_ollama():
    import httpx
    model = os.environ.get('OLLAMA_MODEL', 'llama3')
    response = httpx.get(os.environ.get('OLLAMA_BASE_URL', 'http://127.0.0.1:11434').rstrip('/') + '/api/tags', timeout=3)
    response.raise_for_status()
    installed = {item['name'] for item in response.json().get('models', [])}
    if model not in installed and model + ':latest' not in installed:
        raise RuntimeError('The configured Ollama model is not installed')


class Question(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    mode: str | None = None


def load_runtime(app):
    path = Path(os.environ.get('MEET_INVENTORY_PATH', str(storage() / 'meet_inventory.json')))
    if not path.exists():
        raise RuntimeError('Prepare the selected document inventory before starting backend.meet_main')
    inventory = json.loads(path.read_text())
    engine = importlib.import_module('backend.meet_engine.rag_chat')
    from backend.meet_engine.clean_text import clean_markdown
    from backend.meet_engine.chunk_docs import chunk_documents
    manager = install_meet_lifecycle(app, engine, inventory, clean_markdown,
                                      chunk_documents, storage() / 'meet-releases')
    current = manager.current()
    if not (manager.folder / current['release_id'] / 'chroma').exists():
        manager.change('Build the initial approved production corpus')
    return engine, manager


def citation_for(result, records, release_id):
    doc = result['doc']
    metadata = doc.metadata
    source = metadata.get('source')
    row = next((r for r in records if r.get('source_metadata', {}).get('source') == source
                and r['usage'] == 'production' and r['approval_status'] == 'approved'
                and r['retrieval_enabled']), None)
    if row is None:
        return None
    page = metadata.get('page')
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = None
    from urllib.parse import quote
    return {'document_id': row['document_id'], 'document_title': row['title'],
            'section': None, 'page': page, 'evidence_text': doc.page_content,
            'authority_score': row['authority_level'], 'approval_status': row['approval_status'],
            'version': row['version'],
            'source_url': '/api/documents/'+quote(row['document_id'], safe='')+'/file?release_id='+release_id}


def answer(runtime, question):
    engine, manager = runtime
    started = time.perf_counter()
    # Meet's selected implementation keeps per-query evidence in module globals.
    with manager.lock:
        release = manager.current()
        text = engine.ask_question(question)
        abstained = engine.model_abstained(text)
        selected = getattr(engine, '_LAST_CITATION_RESULTS', [])
        citations = [citation for result in selected
                     if (citation := citation_for(result, release['records'], release['release_id']))]
        # Never present a generated policy answer without the engine's final
        # selected, approved evidence. Do not substitute an arbitrary top hit.
        if not abstained and not citations:
            text, abstained = engine.ABSTENTION_TEXT, True
        conflict = engine.select_relevant_conflict(question, engine.get_current_conflicts())
        return {'answer': text, 'citations': [] if abstained else citations,
                'abstained': abstained,
                'abstention_reason': 'The selected engine could not provide a supported answer.' if abstained else None,
                'confidence': None, 'conflict_status': 'possible' if conflict else 'none',
                'conflict_scope': None, 'conflicts': [], 'conflicting_evidence': [],
                'conflicting_normative_terms': [], 'interpretations': [], 'authority_scores': {},
                'higher_authority_evidence': None, 'resolution_basis': None,
                'human_review_required': bool(conflict),
                'review_notice': 'The selected engine reported a possible rule conflict. Review the answer and original sources with an authorised reviewer.' if conflict else None,
                'mode': 'hybrid_llm', 'requested_mode': 'hybrid_llm', 'fallback_reason': None,
                'latency_ms': round((time.perf_counter()-started)*1000, 2)}


def create_app(runtime_factory=load_runtime):
    @asynccontextmanager
    async def lifespan(app):
        app.state.meet_runtime = runtime_factory(app)
        yield

    app = FastAPI(title='IEEE SMCS selected team chatbot', lifespan=lifespan)
    install_admin(app)

    @app.get('/', include_in_schema=False)
    def home():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(os.environ.get('WEB_FRONTEND_URL', 'http://localhost:3000'))

    @app.get('/api/health/live')
    def live():
        return {'status': 'ok'}

    @app.get('/api/health')
    @app.get('/api/health/ready')
    def health(request: Request):
        engine, _ = request.app.state.meet_runtime
        return {'status': 'ok', 'default_mode': 'hybrid_llm', 'development_mode': False,
                'engine_label': 'BGE + Llama 3',
                'capabilities': {'audit': False, 'evaluation': False, 'admin': True},
                'embedding': {'backend': 'bge', 'model': engine.EMBEDDING_MODEL}}

    @app.get('/api/documents')
    def documents(request: Request):
        _, manager = request.app.state.meet_runtime
        return [{key: row.get(key) for key in ('document_id', 'title', 'version', 'document_type',
                 'approval_status', 'usage', 'retrieval_enabled', 'authority_level')}
                for row in manager.current()['records']]

    @app.get('/api/documents/{identifier}/file')
    def source(identifier: str, release_id: str, request: Request):
        _, manager = request.app.state.meet_runtime
        try:
            release = manager.release(release_id)
        except ValueError:
            raise HTTPException(404, 'Source release not found') from None
        row = next((r for r in release['records'] if r['document_id'] == identifier and
                    r['usage'] == 'production' and r['approval_status'] == 'approved' and r['retrieval_enabled']), None)
        if not row or not Path(row['source_path']).is_file():
            raise HTTPException(404, 'Source not found')
        return FileResponse(row['source_path'], media_type='application/pdf',
                            headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})

    @app.post('/api/chat')
    def chat(data: Question, request: Request):
        if data.mode not in (None, 'hybrid_llm'):
            raise HTTPException(422, 'This deployment uses the selected BGE/Llama engine only')
        try:
            check_ollama()
            return answer(request.app.state.meet_runtime, data.question)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Selected engine answer failed')
            raise HTTPException(503, 'Answer service unavailable. Check the configured Ollama server and model.') from None

    @app.post('/ask')
    def ask(data: dict, request: Request):
        return chat(Question(question=data.get('question') or data.get('query') or ''), request)

    return app


app = create_app()
