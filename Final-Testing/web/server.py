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

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
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

DEMO_MODE = os.environ.get("RAG_DEMO_MODE", "").lower() in ("1", "true", "yes")

# rag_chat.py uses relative paths ("chroma_db") and sibling imports.
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(SRC_DIR))

print(f"Python:         {sys.executable}")
print(f"Project folder: {PROJECT_DIR}")
print(f"rag_chat.py:    {SRC_DIR / 'rag_chat.py'}"
      + ("" if (SRC_DIR / "rag_chat.py").exists() else "  (NOT FOUND)"))
print(f"chroma_db:      {PROJECT_DIR / 'chroma_db'}"
      + ("" if (PROJECT_DIR / "chroma_db").exists() else "  (NOT FOUND - run ingest first)"))
print(f"PDF documents:  {DATA_DIR}"
      + ("" if DATA_DIR.exists() else "  (NOT FOUND)"))


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

    def load(self):
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

        self._module = rag_chat
        print(
            f"\nPipeline ready in {time.perf_counter() - started:.0f}s. "
            "Open http://localhost:8000\n"
        )

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
        # must run one at a time.
        with self._lock:
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

    def load(self):
        # RAG_DEMO_LOAD_DELAY simulates a slow model load for testing.
        time.sleep(float(os.environ.get("RAG_DEMO_LOAD_DELAY", "0")))
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
    threading.Thread(target=pipeline.load, daemon=True).start()
    yield


app = FastAPI(title="IEEE SMCS Governance Assistant", lifespan=lifespan)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@app.get("/api/health")
def health():
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


@app.get("/api/documents")
def documents():
    return sorted(
        DOCUMENTS.values(),
        key=lambda d: (
            list(CATEGORY_LABELS).index(d["category"])
            if d["category"] in CATEGORY_LABELS else 99,
            d["name"].lower(),
        ),
    )


@app.post("/api/chat")
def chat(request: ChatRequest):
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


if DATA_DIR.exists():
    app.mount("/files", StaticFiles(directory=DATA_DIR), name="files")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    print(f"\nStarting web server on http://localhost:{port}\n")
    uvicorn.run(app, host="127.0.0.1", port=port)
