"""Small admin console. Uploads stay outside the production document corpus."""
import base64
import binascii
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
from threading import RLock
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from pypdf import PdfReader

MAX_PDF_BYTES = 8 * 1024 * 1024
MAX_UPLOADS = 100
router = APIRouter()


class PendingPDF(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    version: str = Field(min_length=1, max_length=80)
    content_base64: str = Field(max_length=((MAX_PDF_BYTES + 2) // 3) * 4)


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
        return {"started_at": state.started_at, "requests": dict(state.requests),
                "errors": dict(state.errors), "documents": documents,
                "indexed_chunks": len(search.chunks) if search else None,
                "pending_uploads": pending_records(storage()),
                "search_activation": "Not connected; pending uploads are never indexed automatically"}


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
