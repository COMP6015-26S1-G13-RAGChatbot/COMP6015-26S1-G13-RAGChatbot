"""
Web server for the IEEE SMCS RAG chatbot.

Wraps the existing pipeline in src/rag_chat.py (unchanged) with a small
FastAPI app and serves the browser front end from web/static.

Run from the Final-Testing folder:

    uvicorn web.server:app --port 8000

Then open http://localhost:8000

Set RAG_DEMO_MODE=1 to preview the interface without Ollama or the
vector database (returns canned responses).
"""

import contextlib
import io
import os
import sys
import threading
import time
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
PROJECT_DIR = WEB_DIR.parent
SRC_DIR = PROJECT_DIR / "src"
DATA_DIR = PROJECT_DIR / "data"
STATIC_DIR = WEB_DIR / "static"

DEMO_MODE = os.environ.get("RAG_DEMO_MODE", "").lower() in ("1", "true", "yes")

# rag_chat.py uses relative paths ("chroma_db") and sibling imports.
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(SRC_DIR))


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
        try:
            import rag_chat
        except Exception as exc:  # surfaced through /api/health
            self.error = f"{type(exc).__name__}: {exc}"
            return

        self._module = rag_chat

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
    ready = True
    error = None

    def load(self):
        pass

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


# ============================================================
# API
# ============================================================

app = FastAPI(title="IEEE SMCS Governance Assistant")


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


@app.on_event("startup")
def startup():
    # Load models in the background so the page is reachable immediately.
    threading.Thread(target=pipeline.load, daemon=True).start()


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
