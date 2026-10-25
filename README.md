# IEEE/SMCS Governance RAG Chatbot

A local Retrieval-Augmented Generation (RAG) prototype for answering questions about IEEE and SMCS governance documents. The selected application combines BGE embeddings, ChromaDB, custom semantic and lexical retrieval, rule-based conflict checks, and Llama 3 through Ollama.

The project includes a Next.js chatbot interface and a FastAPI administrator console for document review and activation. Supported answers include source and page metadata. Citation correctness remains a known limitation and requires separate verification.

## Project Status

- **Selected backend:** `backend.meet_main:app`.
- **Methodology:** Iterative development and evaluation of the selected prototype.
- **Deployment:** Local demonstration and deployment configuration are available. Public deployment acceptance testing remains pending.
- **Evaluation:** A saved 50-question development run, with separate answer, retrieval, citation, conflict, authority, and abstention checks.
- **Validation:** Development questions were reused during refinement. Independent governance expert validation remains pending.

The recorded scores do not establish human-level reliability or production readiness.

## Tech Stack

| Component | Current implementation |
| --- | --- |
| Backend | Python, FastAPI, Uvicorn |
| Document processing | pypdf in the current document lifecycle adapter, LangChain text splitters |
| Embeddings | `BAAI/bge-small-en-v1.5`, running on CPU |
| Vector database | ChromaDB, stored locally |
| Retrieval | Semantic search combined with custom lexical scoring |
| Answer generation | Llama 3 through local Ollama, with deterministic handling for selected questions |
| Frontend | Next.js 16, React 19, Tailwind CSS 4 |
| Administration | FastAPI administrator console with login and document lifecycle management |
| Evaluation | Saved development CSV results and custom evaluation checks |

The selected backend does not require Gemini or OpenAI API keys. Its reported evaluation uses custom checks rather than RAGAS metrics. Retrieval uses custom scoring rather than a cross-encoder reranker.

## System Architecture

### 1. Document Preparation

PDF text is extracted and cleaned page by page. `RecursiveCharacterTextSplitter` creates chunks of **1,500 characters**, with **200 characters of overlap**. These settings use characters, not tokens, and overlap does not extend across page boundaries.

Each chunk retains the source filename, page number, source type, authority fields, chunk ID, and position within its page. BGE produces embeddings, and Chroma stores the text, vectors, and metadata.

The current lifecycle adapter uses pypdf. The historical experiment used a different extraction workflow, so page coverage and chunk counts can differ.

### 2. Retrieval and Evidence Selection

1. Retrieve up to **15 global semantic candidates**.
2. Abstain if there are no usable distances or the best distance is greater than **0.75**.
3. Retrieve up to **15 authoritative semantic candidates** and **5 authoritative lexical candidates**.
4. Merge candidates using the selected engine's scoring formula:

   ```text
   semantic_score = max(0, 1 - distance)
   hybrid_score = 2 * semantic_score + lexical_score
   ```

   Lexical-only candidates use a semantic score of zero. Lexical scores include matching terms, phrases, and manually defined topic bonuses.

5. Remove repeated source-page pairs and retain up to **6 authoritative passages**.
6. Retain up to **2 supporting passages** when eligible non-authoritative sources exist in the index.

The distance threshold is a retrieval gate, not a confidence percentage. The current production index excludes draft and synthetic evaluation sources.

### 3. Conflict Handling and Generation

The detector extracts recognised claims about topics including proxy voting, quorum, reporting frequency, and governance hierarchy. It checks predefined opposing claim pairs and uses authority metadata to identify a controlling source where possible.

The engine normally selects up to **2 authoritative passages** for answer generation. It uses Llama 3 through Ollama with temperature zero, while selected questions use deterministic responses. The final response includes at most **1 citation**, selected from evidence metadata.

The API withholds an otherwise supported-looking answer if no approved final citation can be mapped. If Ollama is unavailable or the configured model is missing, the chat endpoint returns HTTP 503.

## Current Document Inventory

The initial inventory in `backend/prepare_meet_sources.py` contains:

| Document | Configured authority rank | Initially searchable |
| --- | ---: | --- |
| IEEE Constitution and Bylaws | 100 | Yes |
| SMCS Constitution and Bylaws | 90 | Yes |
| SMCS Technical Manual | 80 | Yes |
| Financial Operations Manual | 80 | No |

These are the current integration's configured ranks. The Financial Operations Manual remains disabled because successful text extraction was not established. Review source approval and authority assignments with the supervisor before public use.

A document enters production retrieval only when all three conditions hold:

```text
usage = production
approval_status = approved
retrieval_enabled = true
```

An existing local verification produced **274 chunks** from the enabled production documents. This is an observed count, not a fixed requirement. The historical mixed-corpus experiment reported **511 chunks** and included additional draft and test material.

## Repository Structure

```text
backend/
  meet_main.py                 # Selected FastAPI application
  meet_engine/                 # Selected retrieval, generation and conflict code
  prepare_meet_sources.py      # Prepare pinned source PDFs and inventory
  admin_start.py               # Interactive account setup and local server startup
  admin_accounts.py            # Local account creation and password reset
  admin_auth.py                # Authentication and session handling
  admin.py                     # Administrator API routes
  admin_console.html           # Administrator interface
  services/
    meet_admin_adapter.py      # Connect document lifecycle to the selected engine
    admin_lifecycle.py         # Document releases and index switching
  scripts/
    demo_report.py             # Methodology and recorded-results terminal demo
frontend/                      # Next.js chatbot interface and API proxy
tests/                         # Application and integration tests
reports/
  demo_evidence/               # Historical evaluation CSV, summary and checksums
  Report_Demo_Guide.md         # Terminal demonstration guide
deployment/                    # Deployment instructions and startup script
requirements.meet.txt          # Selected backend dependencies
Dockerfile.meet                # Selected backend container configuration
compose.meet.yaml              # Backend and Ollama services
```

The repository also retains earlier experimental code under `backend/main.py`, other services, and `experiments/`. Those workflows are separate from the selected application. Its frontend hides unsupported legacy audit and evaluation views.

## Getting Started

Run the commands below from the project root. These examples use macOS/Linux shell syntax and a Python virtual environment named `venv`. Install Python, a Node.js version supported by the frontend dependencies, and Ollama first.

### 1. Install Dependencies

```bash
git clone https://github.com/COMP6015-26S1-G13-RAGChatbot/COMP6015-26S1-G13-RAGChatbot.git
cd COMP6015-26S1-G13-RAGChatbot
python3 -m venv venv
./venv/bin/pip install -r requirements.meet.txt
npm ci --prefix frontend
```

### 2. Prepare Source Documents

If `.admin_data/meet_inventory.json` does not exist:

```bash
./venv/bin/python -m backend.prepare_meet_sources --output .admin_data
```

This reads the pinned PDF sources from local Git objects. If those objects are unavailable, use the explicit download option:

```bash
./venv/bin/python -m backend.prepare_meet_sources --download --output .admin_data
```

If the inventory already exists, review it and use the administrator workflow for updates. Do not recreate or overwrite it to apply document changes.

### 3. Prepare Local Models

Start Ollama if it is not already running:

```bash
ollama serve
```

In another terminal, download the generation model:

```bash
ollama pull llama3
```

The BGE embedding model must also be cached locally. The engine defaults to loading local model files only. On a first startup with internet access, explicitly allow the initial embedding-model download:

```bash
MEET_ALLOW_MODEL_DOWNLOAD=1 HF_HUB_OFFLINE=0 ./venv/bin/python -m backend.admin_start
```

This command also performs the administrator setup and starts the backend described below. After the model is cached, subsequent runs can use the normal startup command. Do not run two backends on the same port.

### 4. Start the Backend and Create the Administrator Account

```bash
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export OLLAMA_MODEL=llama3
export WEB_FRONTEND_URL=http://localhost:3000
./venv/bin/python -m backend.admin_start
```

On the first run, enter a username and a password of at least 12 characters. Password input is hidden. Subsequent runs reuse the saved account. This startup path loads cached model files and binds the backend to `127.0.0.1:8000`.

The account uses a salted scrypt password hash in private local storage. Sessions last eight hours and end on sign-out, password reset, or server restart. The current implementation supports one configured administrator account and one backend worker.

To reset the local account credentials:

```bash
./venv/bin/python -m backend.admin_accounts --reset-password
```

### 5. Start the Frontend

In another terminal:

```bash
BACKEND_URL=http://127.0.0.1:8000 npm run dev --prefix frontend
```

| Interface | Local URL |
| --- | --- |
| Chatbot | <http://localhost:3000> |
| Administrator console | <http://127.0.0.1:8000/admin> |
| FastAPI documentation | <http://127.0.0.1:8000/docs> |
| Backend readiness | <http://127.0.0.1:8000/api/health> |

The frontend proxies `/api/*` to FastAPI. Its `/admin` link redirects directly to the backend.

### Environment Configuration

Set these values in the process environment used to start the relevant service:

| Variable | Default or purpose |
| --- | --- |
| `OLLAMA_BASE_URL` | Local Ollama endpoint, normally `http://127.0.0.1:11434` |
| `OLLAMA_MODEL` | `llama3` |
| `WEB_FRONTEND_URL` | Frontend URL used by the backend navigation link |
| `BACKEND_URL` | Backend origin used by the Next.js server |
| `ADMIN_STORAGE_DIR` | Private administrator and document storage, default `.admin_data` |
| `ADMIN_COOKIE_SECURE` | Use `0` for local HTTP and `1` when serving over HTTPS |
| `MEET_ALLOW_MODEL_DOWNLOAD` | Default `0`; set to `1` to permit initial embedding-model download |
| `HF_HUB_OFFLINE` | Normal `admin_start` runs default to `1`; set to `0` when deliberately downloading |

## Administrator Workflow

1. Sign in at `/admin`.
2. Inspect document inventory, approval status, and retrieval inclusion.
3. Upload a PDF for review.
4. Approve or reject it with a recorded reason.
5. Activate approved content to update the search collection.

The lifecycle also supports document replacement, disabling retrieval, and restoring a previous release. Approval and activation are separate decisions. Source links include the release ID to preserve the source associated with an earlier answer.

Private account files, sessions, uploaded documents, and local index data belong under private storage and must not be committed.

## Recorded Development Evaluation

The saved evaluation contains **50 questions**: **25 factual**, **15 conflict-related**, and **10 out-of-scope**. These questions were reused during development. Expected answers and labels have not received independent SMCS governance expert validation.

| Measure | Passed / evaluated | Recorded result |
| --- | ---: | ---: |
| Answer accuracy | 48/50 | 96.00% |
| Factual answers | 25/25 | 100.00% |
| Conflict answers | 13/15 | 86.67% |
| Out-of-scope answers | 10/10 | 100.00% |
| Abstention decisions | 50/50 | 100.00% |
| Retrieval source | 37/38 | 97.37% |
| Retrieval page | 29/31 | 93.55% |
| Citation source | 36/38 | 94.74% |
| Citation page | 23/31 | 74.19% |
| Conflict detection | 45/50 | 90.00% |
| Authority resolution | 11/12 | 91.67% |
| Full pipeline | 38/50 | 76.00% |

Average semantic similarity was **0.8228**, with **zero recorded execution errors**. Conflict detection recorded 13 true positives, 32 true negatives, 3 false positives, and 2 false negatives.

These measures use different applicable cases. They are not interchangeable accuracy estimates. The historical evaluation included draft and synthetic sources that are absent from the current production corpus, so it does not establish the current deployment's performance.

The preserved CSV and summary come from `Final-Testing/evaluation/` at commit `cedfa0de15c8ec2a63d5330b000b6a2c744d7d58`. Their original paths and SHA-256 checksums are recorded in `reports/demo_evidence/provenance.json`.

## Terminal Demonstration

Inspect current-corpus retrieval scores, selected evidence, and a live answer:

```bash
./venv/bin/python -m backend.scripts.demo_report methodology --generate
```

Omit `--generate` to inspect retrieval without calling the answer-generation stage. The live command loads the current document release and can take time to initialise the embedding model.

Run the actual conflict detector on an explicitly synthetic fixture:

```bash
./venv/bin/python -m backend.scripts.demo_report conflict
```

Recompute metrics from saved evaluation rows and inspect an individual recorded case:

```bash
./venv/bin/python -m backend.scripts.demo_report results
./venv/bin/python -m backend.scripts.demo_report results --case F01
```

The `results` command checks the preserved files' checksums and aggregates stored judgements. It does not rerun the model or independently rescore answers.

See [the demonstration guide](reports/Report_Demo_Guide.md) for presentation steps.

## Verification

Focused backend checks:

```bash
./venv/bin/python -m unittest tests.test_meet_web tests.test_admin tests.test_admin_auth tests.test_admin_start tests.test_admin_lifecycle tests.test_report_demo
```

Frontend checks:

```bash
npm test --prefix frontend
npm run lint --prefix frontend
npm run build --prefix frontend
```

These commands test application behaviour and build integrity. They do not establish general governance answer accuracy.

## Limitations and Governance

- A correct answer can still cite an incorrect or incomplete page. The current final response exposes at most one citation, including for conflict-related answers.
- Conflict detection covers predefined wording patterns and can miss unfamiliar language, conditions, exceptions, or evidence omitted by retrieval.
- Authority ranks help compare relevant rules but do not replace interpretation by a qualified governance reviewer.
- The Financial Operations Manual remains outside search because successful extraction was not established.
- Local document storage and local model inference support local operation. Initial dependency, model, or source downloads require network access.
- The saved development scores do not measure performance on independent new questions or establish production readiness.
- Public deployment requires additional operational verification, including HTTPS, access controls, backups, and appropriate model-host capacity.

See [deployment instructions](deployment/README.md) for Docker Compose and frontend hosting configuration. The repository contains deployment configuration, not evidence of a completed public deployment.

---

**COMP6015 Group 13 — Master of Computing Project**
