"""
Web server for the IEEE SMCS RAG chatbot.

Wraps the existing pipeline in src/rag_chat.py (unchanged) with a small
FastAPI app and serves the browser front end from web/static.

Run from the project folder (Final-Testing, or your own RAG folder),
using the same Python you use for rag_chat.py:

    python web/server.py

Then open http://localhost:8000

Set RAG_DEMO_MODE=1 to preview the interface without Ollama or the
vector database (returns canned responses).

Sign-in is required by default (accounts are stored in web/users.db).
RAG_ALLOW_SIGNUP=0 hides the "Create account" option, so only accounts
made with `python web/auth.py add <name>` can sign in. RAG_AUTH=0 turns
sign-in off entirely.

The administrator console (web/admin, from the feat/admin-login branch) is
at /admin. Set ADMIN_ACCESS_TOKEN to a random value of 32+ characters to
unlock it; see the README for details.
"""

import contextlib
import importlib.util
import io
import os
import sys
import threading
import time
import traceback
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


# ============================================================
# PATHS
# ============================================================

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"

# The project folder is the one containing web/, unless RAG_PROJECT_DIR
# points somewhere else.
PROJECT_DIR = Path(
    os.environ.get("RAG_PROJECT_DIR", WEB_DIR.parent)
).expanduser().resolve()

# rag_chat.py may live in src/ or directly in the project folder.
SRC_DIR = (
    PROJECT_DIR / "src"
    if (PROJECT_DIR / "src" / "rag_chat.py").exists()
    else PROJECT_DIR
)
DATA_DIR = PROJECT_DIR / "data"

def env_flag(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


DEMO_MODE = env_flag("RAG_DEMO_MODE", False)
AUTH_ENABLED = env_flag("RAG_AUTH", True)
ALLOW_SIGNUP = env_flag("RAG_ALLOW_SIGNUP", True)
COOKIE_SECURE = env_flag("RAG_COOKIE_SECURE", False)  # set to 1 when served over HTTPS
USERS_DB = Path(os.environ.get("RAG_USERS_DB", WEB_DIR / "users.db"))
SESSION_COOKIE = "smcs_session"

# rag_chat.py uses relative paths ("chroma_db") and sibling imports.
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(SRC_DIR))

# Load web/auth.py by path so a same-named module in the project can't shadow it.
_auth_spec = importlib.util.spec_from_file_location("smcs_web_auth", WEB_DIR / "auth.py")
_auth = importlib.util.module_from_spec(_auth_spec)
_auth_spec.loader.exec_module(_auth)
SESSION_SECONDS, AuthError, UserStore = _auth.SESSION_SECONDS, _auth.AuthError, _auth.UserStore


def load_package(name, folder):
    spec = importlib.util.spec_from_file_location(
        name, folder / "__init__.py", submodule_search_locations=[str(folder)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Administrator console. Keep its private data next to the project (not inside
# web/) so replacing the web folder does not delete document releases.
os.environ.setdefault("ADMIN_STORAGE_DIR", str(PROJECT_DIR / ".admin_data"))
ADMIN_TOKEN_SET = len(os.environ.get("ADMIN_ACCESS_TOKEN", "")) >= 32
admin_console = admin_adapter = admin_lifecycle_module = admin_integration = None
ADMIN_IMPORT_ERROR = None
try:
    load_package("smcs_web_admin", WEB_DIR / "admin")
    admin_console = importlib.import_module("smcs_web_admin.admin")
    admin_adapter = importlib.import_module("smcs_web_admin.meet_admin_adapter")
    admin_lifecycle_module = importlib.import_module("smcs_web_admin.admin_lifecycle")
    _spec = importlib.util.spec_from_file_location(
        "smcs_admin_integration", WEB_DIR / "admin_integration.py")
    admin_integration = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(admin_integration)
except ImportError as exc:
    ADMIN_IMPORT_ERROR = f"{exc.name or exc} is not installed"

print(f"Python:         {sys.executable}")
print(f"Project folder: {PROJECT_DIR}")
print(f"rag_chat.py:    {SRC_DIR / 'rag_chat.py'}"
      + ("" if (SRC_DIR / "rag_chat.py").exists() else "  (NOT FOUND)"))
print(f"chroma_db:      {PROJECT_DIR / 'chroma_db'}"
      + ("" if (PROJECT_DIR / "chroma_db").exists() else "  (NOT FOUND - run ingest first)"))
print(f"PDF documents:  {DATA_DIR}"
      + ("" if DATA_DIR.exists() else "  (NOT FOUND)"))
print("Sign-in:        "
      + ((f"on ({USERS_DB.name}"
          + (", sign-up open)" if ALLOW_SIGNUP else ", sign-up closed)"))
         if AUTH_ENABLED else "off (RAG_AUTH=0)"))
print("Admin console:  "
      + (f"unavailable ({ADMIN_IMPORT_ERROR}; run: python -m pip install pypdf)"
         if ADMIN_IMPORT_ERROR else
         "/admin (unlocked with ADMIN_ACCESS_TOKEN)" if ADMIN_TOKEN_SET else
         "/admin (locked: set ADMIN_ACCESS_TOKEN to use it)"))


# ============================================================
# DOCUMENT CATALOGUE
# ============================================================

CATEGORY_LABELS = {
    "authoritative": "Authoritative",
    "draft": "Draft",
    "derived": "Derived",
    "synthetic": "Synthetic",
}


def build_document_index():
    index = {}

    if not DATA_DIR.exists():
        return index

    for pdf in sorted(DATA_DIR.rglob("*.pdf")):
        category = pdf.parent.name
        index[pdf.name.lower()] = {
            "name": pdf.name,
            "category": category,
            "label": CATEGORY_LABELS.get(category, category.title()),
            "url": "/files/" + quote(pdf.relative_to(DATA_DIR).as_posix()),
        }

    return index


DOCUMENTS = build_document_index()


def describe_source(source, page=None, source_type=None):
    name = os.path.basename(str(source or "Unknown"))
    info = DOCUMENTS.get(name.lower(), {})
    url = info.get("url")

    # After an admin activates a new version, link to that release's PDF.
    manager = getattr(globals().get("pipeline"), "lifecycle", None)
    if manager:
        row = admin_integration.release_record_for(manager, name)
        if row:
            url = "/api/sources/" + quote(row["document_id"], safe="")

    if url and page not in (None, "", -1):
        url = f"{url}#page={page}"

    return {
        "source": name,
        "page": page,
        "category": source_type or info.get("category", "unknown"),
        "url": url,
    }


# ============================================================
# PIPELINE ADAPTER
# ============================================================

# Import name -> pip package name, for everything rag_chat.py needs.
REQUIRED_PACKAGES = {
    "langchain_community": "langchain-community",
    "langchain_huggingface": "langchain-huggingface",
    "langchain_core": "langchain-core",
    "chromadb": "chromadb",
    "sentence_transformers": "sentence-transformers",
}


class RagPipeline:
    """
    Calls rag_chat.ask_question and captures the citations and conflicts
    it would normally only print to the terminal.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._module = None
        self.error = None
        self.lifecycle = None

    def load(self, app=None):
        print("\nLoading the RAG pipeline (embedding model + vector database)...")
        print("The first start can take a few minutes while the model downloads.\n")
        started = time.perf_counter()

        missing = [
            package
            for module, package in REQUIRED_PACKAGES.items()
            if importlib.util.find_spec(module) is None
        ]
        if missing:
            command = f'"{sys.executable}" -m pip install ' + " ".join(missing)
            self.error = (
                "Missing packages in this Python environment: "
                + ", ".join(missing)
                + ". Install them with: " + command
            )
            print(f"\n{self.error}\n")
            print("If rag_chat.py works for you, start this server with that same")
            print("Python instead, e.g. activate your virtual environment and run:")
            print("    python web/server.py\n")
            return

        try:
            import rag_chat
        except BaseException as exc:  # surfaced through /api/health
            traceback.print_exc()
            self.error = f"{type(exc).__name__}: {exc}"
            print(f"\nPipeline failed to load: {self.error}\n")
            return

        # Connect the admin console first, so "ready" means fully ready.
        if app is not None:
            self.connect_admin(app, rag_chat)
        self._module = rag_chat
        print(
            f"\nPipeline ready in {time.perf_counter() - started:.0f}s. "
            "Open http://localhost:8000\n"
        )

    def connect_admin(self, app, engine):
        """Give the admin console's document lifecycle access to the engine.

        Until an administrator activates, excludes, rebuilds or restores
        something, the engine keeps using the original chroma_db.
        """
        if admin_adapter is None or not ADMIN_TOKEN_SET:
            return
        try:
            import chunk_docs
            import clean_text
            import parse_pdf

            folder = admin_console.storage()
            # Not in the storage root: the console reads every *.json there
            # as an uploaded-PDF record.
            inventory_file = folder / "inventory" / "inventory.json"
            inventory_file.parent.mkdir(mode=0o700, exist_ok=True)
            inventory, created = admin_integration.load_inventory(
                inventory_file, DATA_DIR, parse_pdf,
                admin_lifecycle_module.atomic_json)
            self.lifecycle = admin_adapter.install_meet_lifecycle(
                app, engine, inventory, clean_text.clean_markdown,
                chunk_docs.chunk_documents, folder / "releases")
            print(f"Admin console connected: {len(inventory)} documents"
                  + (f" (inventory created at {inventory_file})" if created else ""))
        except Exception as exc:
            traceback.print_exc()
            print(f"\nAdmin document management not connected: {type(exc).__name__}: {exc}"
                  "\nThe chatbot works normally; the console can still be opened.\n")

    @property
    def ready(self):
        return self._module is not None

    def ask(self, question):
        module = self._module
        captured = {"citations": [], "conflicts": []}

        original_citations = module.print_citations
        original_conflicts = module.print_conflict_report

        def capture_citations(results):
            captured["citations"] = list(results or [])
            original_citations(results)

        def capture_conflicts(conflicts):
            captured["conflicts"] = list(conflicts or [])
            original_conflicts(conflicts)

        trace = io.StringIO()

        # rag_chat keeps per-query state in module globals, so queries
        # must run one at a time. With the admin console connected, they
        # also share its lock so an index switch never overlaps a question.
        lifecycle_lock = self.lifecycle.lock if self.lifecycle else contextlib.nullcontext()
        with lifecycle_lock, self._lock:
            module.print_citations = capture_citations
            module.print_conflict_report = capture_conflicts
            try:
                with contextlib.redirect_stdout(trace):
                    answer = module.ask_question(question)
            finally:
                module.print_citations = original_citations
                module.print_conflict_report = original_conflicts

        abstained = answer.strip() == module.ABSTENTION_TEXT

        citations = []
        for result in captured["citations"]:
            doc = result["doc"]
            meta = doc.metadata
            item = describe_source(
                meta.get("source"),
                meta.get("page"),
                meta.get("source_type"),
            )
            excerpt = " ".join(doc.page_content.split())
            if len(excerpt) > 600:
                excerpt = excerpt[:600].rsplit(" ", 1)[0] + "…"
            item["excerpt"] = excerpt
            citations.append(item)

        conflicts = [
            {
                "type": c.get("conflict_type"),
                "topic": c.get("topic"),
                "a": {
                    **describe_source(c.get("source_a"), c.get("page_a")),
                    "claim": c.get("claim_a"),
                },
                "b": {
                    **describe_source(c.get("source_b"), c.get("page_b")),
                    "claim": c.get("claim_b"),
                },
                "controlling_source": c.get("controlling_source"),
            }
            for c in captured["conflicts"]
        ]

        return {
            "answer": answer,
            "abstained": abstained,
            "citations": [] if abstained else citations,
            "conflicts": conflicts,
            "trace": trace.getvalue(),
        }


class DemoPipeline:
    ready = False
    error = None
    lifecycle = None

    def load(self, app=None):
        # RAG_DEMO_LOAD_DELAY simulates a slow model load for testing.
        time.sleep(float(os.environ.get("RAG_DEMO_LOAD_DELAY", "0")))
        # No engine in demo mode: list the inventory in the admin console
        # read-only; document actions stay disabled.
        if app is not None and admin_integration is not None:
            try:
                import parse_pdf
                rows = admin_integration.build_inventory(DATA_DIR, parse_pdf)
                app.state.admin_document_provider = lambda: [
                    {key: row[key] for key in ("document_id", "title", "version", "approval_status",
                                               "usage", "retrieval_enabled", "authority_level")}
                    for row in rows]
            except Exception as exc:
                print(f"Admin console demo inventory unavailable: {exc}")
        self.ready = True

    def ask(self, question):
        time.sleep(1.2)
        q = question.lower()

        if "weather" in q or "capital" in q or "recipe" in q:
            return {
                "answer": "I cannot determine this from the retrieved documents.",
                "abstained": True,
                "citations": [],
                "conflicts": [],
                "trace": "[demo] Retrieval distance above threshold - abstaining.",
            }

        citation = describe_source(
            "SMC-Constitution-Bylaws-August-2023-web.pdf", 6, "authoritative"
        )
        citation["excerpt"] = (
            "A majority of the voting members of the BoG shall constitute a "
            "quorum. Proxy voting is not allowed, and a proxy shall not be "
            "counted in determining a quorum."
        )

        conflicts = []
        if "quorum" in q or "proxy" in q:
            conflicts = [{
                "type": "numeric_threshold",
                "topic": "bog_quorum",
                "a": {
                    **describe_source(
                        "SMC-Constitution-Bylaws-August-2023-web.pdf", 6
                    ),
                    "claim": "majority of voting members",
                },
                "b": {
                    **describe_source(
                        "SMCS_RAG_Synthetic_Conflict_Stress_Test_Corpus.pdf", 2
                    ),
                    "claim": "one third of voting members",
                },
                "controlling_source": "SMC-Constitution-Bylaws-August-2023-web.pdf",
            }]

        return {
            "answer": (
                "A **majority of the voting members** of the SMCS Board of "
                "Governors constitutes a quorum. Proxy voting is not allowed, "
                "and proxies are not counted when determining a quorum."
            ),
            "abstained": False,
            "citations": [citation],
            "conflicts": conflicts,
            "trace": "[demo] This response was generated in demo mode.",
        }


pipeline = DemoPipeline() if DEMO_MODE else RagPipeline()
STARTED_AT = time.perf_counter()


# ============================================================
# API
# ============================================================

@contextlib.asynccontextmanager
async def lifespan(app):
    # Load models in the background so the page is reachable immediately.
    threading.Thread(target=pipeline.load, args=(app,), daemon=True).start()
    yield


app = FastAPI(title="IEEE SMCS Governance Assistant", lifespan=lifespan)

if admin_console is not None:
    admin_console.install_admin(app)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


# ============================================================
# SIGN-IN
# ============================================================

users = UserStore(USERS_DB)


class Credentials(BaseModel):
    username: str = Field(..., max_length=64)
    password: str = Field(..., max_length=256)


def session_user(request: Request):
    """Username for the request's session cookie, or None."""
    if not AUTH_ENABLED:
        return "guest"
    return users.user_for_session(request.cookies.get(SESSION_COOKIE))


def require_user(request: Request):
    user = session_user(request)
    if user is None:
        raise HTTPException(401, "Sign in required.")
    return user


def start_session(response: Response, user_id, username):
    token = users.create_session(user_id)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )
    return {"username": username}


@app.get("/api/auth/config")
def auth_config():
    return {"auth": AUTH_ENABLED, "signup": AUTH_ENABLED and ALLOW_SIGNUP}


@app.post("/api/login")
def login(credentials: Credentials, response: Response):
    if not AUTH_ENABLED:
        raise HTTPException(400, "Sign-in is turned off on this server.")
    try:
        user_id, username = users.authenticate(credentials.username, credentials.password)
    except AuthError as exc:
        raise HTTPException(exc.status, exc.message)
    return start_session(response, user_id, username)


@app.post("/api/signup")
def signup(credentials: Credentials, response: Response):
    if not (AUTH_ENABLED and ALLOW_SIGNUP):
        raise HTTPException(403, "Creating accounts is turned off. Ask the administrator for an account.")
    try:
        user_id = users.create_user(credentials.username, credentials.password)
    except AuthError as exc:
        raise HTTPException(exc.status, exc.message)
    return start_session(response, user_id, credentials.username.strip())


@app.post("/api/logout")
def logout(request: Request, response: Response):
    users.delete_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/me")
def me(user: str = Depends(require_user)):
    return {"username": user, "auth": AUTH_ENABLED}


@app.get("/api/health")
def health(user: str = Depends(require_user)):
    if pipeline.error:
        status = "error"
    elif pipeline.ready:
        status = "ready"
    else:
        status = "loading"

    return {
        "status": status,
        "loading_seconds": round(time.perf_counter() - STARTED_AT),
        "demo": DEMO_MODE,
        "error": pipeline.error,
        "documents": len(DOCUMENTS),
    }


def release_documents(manager):
    """Searchable documents in the active admin release, for the sidebar."""
    rows = []
    for row in manager.current()["records"]:
        if not (row["usage"] == "production" and row["approval_status"] == "approved"
                and row["retrieval_enabled"]):
            continue
        meta = row.get("source_metadata", {})
        category = meta.get("source_type", "unknown")
        rows.append({
            "name": meta.get("source", row["title"]),
            "category": category,
            "label": CATEGORY_LABELS.get(category, category.title()),
            "url": "/api/sources/" + quote(row["document_id"], safe=""),
        })
    return rows


@app.get("/api/documents")
def documents(user: str = Depends(require_user)):
    manager = getattr(pipeline, "lifecycle", None)
    return sorted(
        release_documents(manager) if manager else DOCUMENTS.values(),
        key=lambda d: (
            list(CATEGORY_LABELS).index(d["category"])
            if d["category"] in CATEGORY_LABELS else 99,
            d["name"].lower(),
        ),
    )


@app.post("/api/chat")
def chat(request: ChatRequest, user: str = Depends(require_user)):
    question = request.question.strip()
    if not question:
        raise HTTPException(400, "Question must not be empty.")

    if pipeline.error:
        raise HTTPException(503, f"Pipeline failed to load: {pipeline.error}")

    if not pipeline.ready:
        raise HTTPException(503, "The assistant is still loading. Try again shortly.")

    started = time.perf_counter()
    try:
        result = pipeline.ask(question)
    except Exception as exc:
        raise HTTPException(500, f"{type(exc).__name__}: {exc}")

    result["latency_ms"] = round((time.perf_counter() - started) * 1000)
    return result


@app.get("/api/sources/{document_id}")
def release_source(document_id: str, user: str = Depends(require_user)):
    # The PDF version in the active admin release (may differ from data/).
    manager = getattr(pipeline, "lifecycle", None)
    row = next((r for r in manager.current()["records"] if r["document_id"] == document_id
                and r["usage"] == "production" and r["approval_status"] == "approved"),
               None) if manager else None
    if not row or not Path(row["source_path"]).is_file():
        raise HTTPException(404, "File not found.")
    return FileResponse(row["source_path"], media_type="application/pdf",
                        headers={"Cache-Control": "private, no-store"})


@app.get("/files/{file_path:path}")
def source_file(file_path: str, user: str = Depends(require_user)):
    # Only serve PDFs that live inside the data folder.
    data_root = DATA_DIR.resolve()
    target = (data_root / file_path).resolve()
    if (
        not target.is_relative_to(data_root)
        or target.suffix.lower() != ".pdf"
        or not target.is_file()
    ):
        raise HTTPException(404, "File not found.")
    return FileResponse(target, media_type="application/pdf")


# The app and sign-in pages depend on the session, so browsers must not
# reuse a cached copy (e.g. showing the app via Back after signing out).
NO_STORE = {"Cache-Control": "no-store"}


@app.get("/")
def index(request: Request):
    if session_user(request) is None:
        return RedirectResponse("/login", status_code=303, headers=NO_STORE)
    return FileResponse(STATIC_DIR / "index.html", headers=NO_STORE)


@app.get("/login")
def login_page(request: Request):
    if not AUTH_ENABLED or session_user(request) is not None:
        return RedirectResponse("/", status_code=303, headers=NO_STORE)
    return FileResponse(STATIC_DIR / "login.html", headers=NO_STORE)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    print(f"\nStarting web server on http://localhost:{port}\n")
    uvicorn.run(app, host="127.0.0.1", port=port)
