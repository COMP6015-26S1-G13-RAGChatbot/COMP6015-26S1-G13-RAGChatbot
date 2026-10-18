"""Small admin console. Uploads stay outside the production document corpus."""
import base64
import binascii
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import logging
from pathlib import Path
import secrets
from threading import RLock
from uuid import uuid4
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field, field_validator
from pypdf import PdfReader
from backend.services.admin_lifecycle import atomic_json

MAX_PDF_BYTES = 8 * 1024 * 1024
MAX_UPLOADS = 100
router = APIRouter()


class PendingPDF(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    version: str = Field(min_length=1, max_length=80)
    content_base64: str = Field(max_length=((MAX_PDF_BYTES + 2) // 3) * 4)


class ReviewDecision(BaseModel):
    decision: Literal['approved', 'rejected']
    reason: str = Field(min_length=5, max_length=1000)
    target_document_id: str | None = Field(default=None, max_length=200)


class ChangeReason(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)

    @field_validator('reason')
    @classmethod
    def meaningful_reason(cls, value):
        if len(value.strip()) < 5:
            raise ValueError('Enter a reason of at least five characters')
        return value.strip()


class RetrievalDecision(ChangeReason):
    enabled: bool


def lifecycle(request):
    service = getattr(request.app.state, 'document_lifecycle', None)
    if not service:
        raise HTTPException(503, 'Document lifecycle adapter is not connected')
    return service


def upload_record(identifier):
    if len(identifier) != 32 or any(c not in '0123456789abcdef' for c in identifier):
        raise HTTPException(404, 'Not found')
    path = storage() / (identifier + '.json')
    if not path.exists():
        raise HTTPException(404, 'Upload not found')
    return path, json.loads(path.read_text())


def record_action(event, identifier, reason):
    try:
        with (storage() / 'audit.jsonl').open('a') as stream:
            stream.write(json.dumps({'event': event, 'id': identifier, 'reason': reason,
                                     'at': datetime.now(timezone.utc).isoformat()}) + '\n')
    except OSError:
        # Published releases retain their reason and timestamp even if this
        # secondary log is unavailable. Do not report a successful switch as failed.
        logging.getLogger(__name__).exception('Admin action log unavailable for %s', event)


def run_change(operation):
    try:
        return operation()
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(422, str(exc)) from None
    except Exception:
        logging.getLogger(__name__).exception('Administrator index operation failed')
        raise HTTPException(503, 'Index update failed; the previous release remains active. Check server logs.') from None


class AdminState:
    def __init__(self):
        self.lock = RLock()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.requests = Counter()
        self.errors = Counter()

    def observe(self, path, status):
        # Aggregate only: never collect questions, IPs, tokens or answer text.
        if path in {"/api/chat", "/ask", "/api/audit"}:
            with self.lock:
                self.requests[path] += 1
                if status >= 400:
                    self.errors[path] += 1


def require_admin(request: Request):
    token = os.environ.get("ADMIN_ACCESS_TOKEN", "")
    if len(token) < 32:
        raise HTTPException(503, "Admin access is not configured")
    supplied = request.headers.get("authorization", "")
    if not secrets.compare_digest(supplied.encode(), ("Bearer " + token).encode()):
        raise HTTPException(401, "Invalid administrator token")


def storage():
    path = Path(os.environ.get("ADMIN_STORAGE_DIR", str(Path(__file__).resolve().parents[1] / ".admin_data")))
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def pending_records(folder):
    return sorted((json.loads(p.read_text()) for p in folder.glob("*.json")),
                  key=lambda r: r["uploaded_at"], reverse=True)


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def console():
    return HTMLResponse(Path(__file__).with_name("admin_console.html").read_text(), headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    })


@router.get("/api/admin/overview", dependencies=[Depends(require_admin)])
def overview(request: Request):
    state = request.app.state.admin
    registry = getattr(request.app.state, "registry", None)
    search = getattr(request.app.state, "search", None)
    # Meet's deployment can supply this adapter without replacing retrieval.
    provider = getattr(request.app.state, "admin_document_provider", None)
    if provider:
        documents = provider()
    elif registry:
        documents = [{"document_id": r.document_id, "title": r.title, "version": r.version,
                      "approval_status": r.approval_status, "usage": r.usage,
                      "retrieval_enabled": r.retrieval_enabled, "authority_level": r.authority_level}
                     for r in registry.list_documents()]
    else:
        documents = []
    with state.lock:
        manager = getattr(request.app.state, 'document_lifecycle', None)
        chunk_provider = getattr(request.app.state, 'admin_chunk_count_provider', None)
        return {"started_at": state.started_at, "requests": dict(state.requests),
                "errors": dict(state.errors), "documents": documents,
                "indexed_chunks": chunk_provider() if chunk_provider else len(search.chunks) if search else None,
                "pending_uploads": pending_records(storage()),
                "lifecycle_enabled": bool(manager),
                "index_status": manager.status if manager else {'state': 'not_connected'},
                "active_release": manager.current()['release_id'] if manager else None,
                "releases": manager.history() if manager else [],
                "search_activation": "Review, then activate to build and publish a new index" if manager else
                    "Not connected; pending uploads are never indexed automatically"}


@router.post('/api/admin/uploads/{identifier}/review', dependencies=[Depends(require_admin)])
def review_upload(identifier: str, decision: ReviewDecision, request: Request):
    if not decision.reason.strip() or len(decision.reason.strip()) < 5:
        raise HTTPException(422, 'Enter a review reason of at least five characters')
    with request.app.state.admin.lock:
        path, record = upload_record(identifier)
        if record['approval_status'] != 'pending':
            raise HTTPException(409, 'This upload has already been reviewed')
        if decision.decision == 'approved':
            manager = lifecycle(request)
            run_change(lambda: manager.target(manager.current()['records'], decision.target_document_id))
            record['target_document_id'] = decision.target_document_id
        record.update(approval_status=decision.decision, review_reason=decision.reason.strip(),
                      reviewed_at=datetime.now(timezone.utc).isoformat())
        # Existing authority is inherited on activation; the request cannot set it.
        atomic_json(path, record)
        record_action('upload_' + decision.decision, identifier, decision.reason.strip())
    return record


@router.post('/api/admin/uploads/{identifier}/activate', dependencies=[Depends(require_admin)])
def activate_upload(identifier: str, data: ChangeReason, request: Request):
    _, record = upload_record(identifier)
    manager = lifecycle(request)
    result = run_change(lambda: manager.activate(record.get('target_document_id'), record,
                                                storage() / (identifier + '.pdf'), data.reason))
    record_action('version_activated', identifier, data.reason)
    return result


@router.post('/api/admin/documents/{identifier}/retrieval', dependencies=[Depends(require_admin)])
def toggle_retrieval(identifier: str, data: RetrievalDecision, request: Request):
    manager = lifecycle(request)
    result = run_change(lambda: manager.toggle(identifier, data.enabled, data.reason))
    record_action('retrieval_enabled' if data.enabled else 'retrieval_disabled', identifier, data.reason)
    return result


@router.post('/api/admin/index/rebuild', dependencies=[Depends(require_admin)])
def rebuild_index(data: ChangeReason, request: Request):
    result = run_change(lambda: lifecycle(request).change(data.reason))
    record_action('index_rebuilt', result['release_id'], data.reason)
    return result


@router.post('/api/admin/releases/{identifier}/restore', dependencies=[Depends(require_admin)])
def restore_release(identifier: str, data: ChangeReason, request: Request):
    result = run_change(lambda: lifecycle(request).change(data.reason, restore=identifier))
    record_action('release_restored', identifier, data.reason)
    return result


@router.post("/api/admin/uploads", dependencies=[Depends(require_admin)], status_code=201)
def upload(data: PendingPDF, request: Request):
    title, version = data.title.strip(), data.version.strip()
    if not title or not version:
        raise HTTPException(422, "Title and version are required")
    try:
        raw = base64.b64decode(data.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "Invalid file encoding") from None
    if len(raw) > MAX_PDF_BYTES:
        raise HTTPException(413, "PDF exceeds the 8 MiB limit")
    if not raw.startswith(b"%PDF-"):
        raise HTTPException(422, "A PDF file is required")
    try:
        reader = PdfReader(io.BytesIO(raw), strict=True)
        if reader.is_encrypted:
            raise ValueError("encrypted")
        pages = len(reader.pages)
        if not 1 <= pages <= 500:
            raise ValueError("page limit")
    except Exception:
        raise HTTPException(422, "PDF must be readable, unencrypted, and contain 1–500 pages") from None
    folder = storage()
    with request.app.state.admin.lock:
        if len(list(folder.glob("*.json"))) >= MAX_UPLOADS:
            raise HTTPException(409, "Pending storage is full; ask the operator to archive reviewed files")
        identifier = uuid4().hex
        record = {"id": identifier, "title": title, "version": version, "pages": pages,
                  "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                  "approval_status": "pending", "retrieval_enabled": False,
                  "uploaded_at": datetime.now(timezone.utc).isoformat()}
        pdf_path, meta_path = folder / (identifier + ".pdf"), folder / (identifier + ".json")
        try:
            with pdf_path.open("xb") as f:
                f.write(raw)
            pdf_path.chmod(0o600)
            with meta_path.open("x") as f:
                json.dump(record, f, indent=2)
            meta_path.chmod(0o600)
            with (folder / "audit.jsonl").open("a") as f:
                f.write(json.dumps({"event": "pending_pdf_uploaded", "id": identifier,
                                    "sha256": record["sha256"], "at": record["uploaded_at"]}) + "\n")
            (folder / "audit.jsonl").chmod(0o600)
        except OSError:
            pdf_path.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)
            raise HTTPException(503, "Upload could not be saved") from None
    return record


@router.get("/api/admin/uploads/{identifier}/download", dependencies=[Depends(require_admin)])
def download(identifier: str):
    if len(identifier) != 32 or any(c not in "0123456789abcdef" for c in identifier):
        raise HTTPException(404, "Not found")
    path = storage() / (identifier + ".pdf")
    if not path.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(path, media_type="application/octet-stream", filename="pending-" + identifier + ".pdf",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/api/admin/audit", dependencies=[Depends(require_admin)])
def audit_log():
    path = storage() / "audit.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()[-100:]]


def install_admin(app):
    app.state.admin = AdminState()
    app.include_router(router)

    @app.middleware("http")
    async def admin_observer(request: Request, call_next):
        # Reject oversized upload bodies while streaming, before JSON parsing.
        if request.url.path == "/api/admin/uploads":
            try:
                require_admin(request)
            except HTTPException as exc:
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code,
                                    headers={"Cache-Control": "no-store"})
            limit = ((MAX_PDF_BYTES + 2) // 3) * 4 + 8192
            from starlette.responses import JSONResponse
            body = bytearray()
            async for piece in request.stream():
                body.extend(piece)
                if len(body) > limit:
                    return JSONResponse({"detail": "Upload body too large"}, status_code=413)
            request._body = bytes(body)
        try:
            response = await call_next(request)
        except Exception:
            app.state.admin.observe(request.url.path, 500)
            raise
        app.state.admin.observe(request.url.path, response.status_code)
        if request.url.path.startswith("/api/admin/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response
