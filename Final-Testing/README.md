# IEEE SMCS Governance RAG Chatbot

**COMP6015/COMP6016 – Group 13 – Master of Computing project (2026)**
Supervisor: Tom Gedeon

A retrieval-augmented generation (RAG) chatbot that answers questions about
the governance documents of the IEEE Systems, Man, and Cybernetics Society
(SMCS). Every answer:

- is grounded in the documents;
- cites the source document and page;
- reports and resolves rules that conflict between documents, using the
  document hierarchy of authority;
- is refused when the documents do not cover the question.

Everything runs locally: Llama 3 through Ollama, BGE embeddings and a
ChromaDB vector store. No document or question leaves the computer.

The delivered system is in **[`Final-Testing/`](Final-Testing/)**. The other
top-level folders are earlier prototypes (see [Repository layout](#repository-layout)).

---

## Contents

1. [Features](#features)
2. [Quick start](#quick-start)
3. [Requirements](#requirements)
4. [Installation](#installation)
5. [Usage](#usage)
6. [How it works](#how-it-works)
7. [Data](#data)
8. [Testing and evaluation](#testing-and-evaluation)
9. [Configuration](#configuration)
10. [Deployment](#deployment)
11. [Security and privacy](#security-and-privacy)
12. [Known issues and limitations](#known-issues-and-limitations)
13. [Troubleshooting](#troubleshooting)
14. [Future work](#future-work)
15. [Repository layout](#repository-layout)
16. [Team and acknowledgements](#team-and-acknowledgements)

---

## Features

| Area | What it does |
| --- | --- |
| Question answering | Natural-language questions answered only from retrieved document text (Llama 3, temperature 0) |
| Citations | Source document and page for each answer, with the quoted passage and a link to that PDF page in the web interface |
| Conflict handling | Detects rules that disagree between documents and states which document controls, by authority rank |
| Abstention | Says "I cannot determine this from the retrieved documents." instead of guessing |
| Hybrid retrieval | Semantic (vector) search combined with lexical (keyword) scoring, with authority-aware selection |
| Evaluation | 50-question Golden Set and an automated evaluation script; RAGAS metrics for an earlier version |
| Web interface | Chat page with sources, conflict tables, saved history, light/dark themes and a phone layout |
| User accounts | Sign-up, sign-in and sign-out; salted password hashes; account command-line tool |
| Admin console | Upload, review, approve and activate new document versions; rebuilds the index safely; restore earlier releases; audit log |

---

## Quick start

Windows PowerShell. Python 3.11+, Git and [Ollama](https://ollama.com) must be
installed first.

```powershell
git clone https://github.com/COMP6015-26S1-G13-RAGChatbot/COMP6015-26S1-G13-RAGChatbot.git
cd COMP6015-26S1-G13-RAGChatbot\Final-Testing

ollama pull llama3                                   # language model, once (~4.7 GB)

python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements-lock.txt       # exact tested versions

python src\ingest.py                                 # build the search index, once
python web\server.py                                 # start the website
```

Open **http://localhost:8000**, choose **Create account**, and ask a question.

On macOS/Linux, use `source venv/bin/activate` and forward slashes in paths.

---

## Requirements

| Item | Version / notes |
| --- | --- |
| Python | 3.11 or newer (the locked packages, e.g. NumPy 2.4, need 3.11+) |
| Ollama | Current version, with the `llama3` model (8B) |
| Git | Any recent version |
| RAM | 16 GB recommended (Llama 3 8B needs about 8 GB on its own) |
| Disk | About 8 GB (model 4.7 GB, Python packages about 1.2 GB, embeddings model, index) |
| GPU | Optional; Ollama uses it automatically when available |
| Browser | Any modern browser (tested in Chromium) |
| Internet | Needed only for installation and the first downloads; then works offline |

---

## Installation

All commands are run from the `Final-Testing` folder.

### 1. Get the code

```powershell
git clone https://github.com/COMP6015-26S1-G13-RAGChatbot/COMP6015-26S1-G13-RAGChatbot.git
cd COMP6015-26S1-G13-RAGChatbot\Final-Testing
```

Or unzip the submitted source archive and open its `Final-Testing` folder.

### 2. Download the language model

Start Ollama (open the app, or run `ollama serve`), then:

```powershell
ollama pull llama3
ollama list          # llama3 should be listed
```

### 3. Create the Python environment

```powershell
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements-lock.txt
```

- `requirements-lock.txt` pins the exact versions of the tested setup. Use it.
- `requirements.txt` lists only the direct dependencies, without versions.
- If PowerShell blocks `activate`, run
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

### 4. Build the search index

```powershell
python src\ingest.py
```

This parses the PDFs in `data/`, then cleans, chunks and embeds them, and
writes the ChromaDB index to `chroma_db/`. The first run also downloads the
embedding model `BAAI/bge-small-en-v1.5`. Re-running it deletes and rebuilds
`chroma_db/`.

---

## Usage

### Web interface (recommended)

```powershell
venv\Scripts\activate
python web\server.py
```

1. Wait for `Pipeline ready` in the terminal.
2. Open http://localhost:8000.
3. Create an account, or sign in.
4. Ask a question. The answer shows its source, quoted text, a link to the
   PDF page and any detected conflict.
5. Use **Sign out** when finished. Stop the server with **Ctrl + C**.

The sidebar keeps your conversation history. It is per user and stored in
the browser.

Example questions (from the Golden Set):

| Type | Question |
| --- | --- |
| Factual | Is proxy voting allowed at an SMCS Board of Governors meeting? |
| Factual | What constitutes a quorum for the SMCS Board of Governors? |
| Factual | Can the SMCS BoG take action without holding a meeting? |
| Conflict | The retrieved documents disagree about proxy voting. What rule should govern? |
| Conflict | A synthetic guide says absent BoG members may appoint voting proxies. Is that governing SMCS policy? |
| Out of scope | Who won the latest AFL premiership? (should be refused) |

### Command-line chatbot

```powershell
python src\rag_chat.py
```

Type a question at the prompt, or `exit` to quit. The terminal shows each
stage: retrieval, authority analysis, conflicts, the answer and the citation.

### User accounts

Accounts are stored in `web/users.db`, which is created automatically.

```powershell
python web\auth.py add alice      # create an account (password is typed hidden)
python web\auth.py passwd alice   # reset a password
python web\auth.py remove alice   # delete an account
python web\auth.py list           # list accounts
```

### Administrator console

The console manages document versions at http://localhost:8000/admin.
It is unlocked with a token (32 or more characters), set before starting
the server:

```powershell
$env:ADMIN_ACCESS_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(48))"
echo $env:ADMIN_ACCESS_TOKEN      # copy it; paste it into the console
python web\server.py
```

| Action | Effect |
| --- | --- |
| Submit a PDF for review | Validated and stored as *pending*; never searched |
| Approve / Reject | Records the decision and a reason |
| Activate version | Builds a new index with that version, checks it, then switches the chatbot to it; on failure the previous index stays active |
| Exclude from search / Enable search | Removes or restores a document in retrieval |
| Rebuild / Restore | Rebuilds the current index, or returns to an earlier release |
| Audit log | Lists every administrator action with its reason |

Admin data is stored in `.admin_data/` next to the project. Back it up.
Never delete `.admin_data/releases` while it is in use.

---

## How it works

```
                         INGESTION (src/ingest.py, run once)
 PDFs in data/  ─►  parse_pdf.py  ─►  clean_text.py  ─►  chunk_docs.py  ─►  BGE embeddings  ─►  ChromaDB
                    (PyMuPDF, page     (whitespace,       (1,500 chars,      (bge-small-        (chroma_db/,
                     text, authority    hyphenation)       200 overlap)       en-v1.5)           metadata)
                     metadata)

                         QUESTION ANSWERING (src/rag_chat.py → ask_question)
 Question ─► global semantic search (k=15) ─► abstain if best distance > 0.75
          ─► authoritative semantic (k=15) + lexical (k=5) search, supporting lexical search
          ─► merge, de-duplicate pages, keep 6 authoritative + 2 supporting results
          ─► conflict detection (conflict_detection.py) and authority resolution
          ─► answer: deterministic for conflicts and known facts, otherwise Llama 3
             with the top 2 passages as context
          ─► one citation (document + page), conflict report
```

### Ingestion

- **Parsing** (`parse_pdf.py`): reads each PDF page with PyMuPDF. Each page
  is tagged with its source file, page number, source type (the sub-folder of
  `data/`) and two authority values:
  - `authority_level`: authoritative 4, draft 3, derived 2, synthetic 1;
  - `authority_rank`: a finer rank per document (below).
- **Cleaning** (`clean_text.py`): joins hyphenated line breaks and normalises
  whitespace.
- **Chunking** (`chunk_docs.py`): LangChain `RecursiveCharacterTextSplitter`,
  1,500 characters with 200 overlap. It splits on paragraphs, lines, sentences,
  then words, and keeps the page and authority metadata on every chunk.
- **Embedding and storage** (`ingest.py`, `embed_store.py`): `BAAI/bge-small-en-v1.5`
  through `langchain-huggingface`, stored in a persistent ChromaDB collection
  in `chroma_db/`.

### Hierarchy of authority

| Rank | Document |
| --- | --- |
| 100 | IEEE Constitution and Bylaws |
| 90 | SMCS Constitution and Bylaws |
| 80 | SMCS Technical Manual; Financial Operations Manual |
| 70 | Other authoritative documents |
| 40 | Draft documents (e.g. draft Operational Manual V5) |
| 20 | Derived test corpus |
| 0 | Synthetic conflict corpus |

When two documents disagree, the higher rank controls. With equal rank, an
authoritative document controls over a non-authoritative one.

### Retrieval and answering

All of this is in `rag_chat.py`.

1. **Abstention check.** A global semantic search returns 15 results. If the
   best vector distance is above `0.75`, the question is treated as out of
   scope and the abstention text is returned.
2. **Hybrid retrieval.** Semantic search (15) and lexical keyword scoring (5)
   over authoritative documents, plus lexical search over supporting
   documents. Results are merged and de-duplicated by page, and the best
   6 authoritative and 2 supporting results are kept.
3. **Conflict detection** (`conflict_detection.py`). Rule-based extraction
   of claims on five governance topics:
   - proxy voting
   - Board of Governors quorum
   - proxies in quorum
   - technical committee reporting frequency
   - governance hierarchy

   Opposing claims across documents are reported, and the controlling
   document is chosen by authority.
4. **Answer generation.** Conflict and authority questions, and some
   well-defined facts, get deterministic answers built from the controlling
   evidence. Otherwise Llama 3 (temperature 0) answers from the top 2
   passages only. A fallback answer is used if the model output is unusable.
5. **Citation.** The single best supporting passage is cited (document and
   page).

### Web application

`Final-Testing/web/` wraps `ask_question` without changing it.

- **Server** (`server.py`): a FastAPI app.
  - It captures the printed citations and conflict report and returns them
    as JSON.
  - It serves the cited PDF pages to signed-in users only.
  - Questions are answered one at a time, because the pipeline keeps
    per-query state.
- **Accounts** (`auth.py`): SQLite with PBKDF2-HMAC-SHA256 password hashes
  and hashed session tokens.
- **Admin console** (`web/admin/`): document lifecycle with versioned
  releases and an atomic switch of the active index.

  [`Final-Testing/README.md`](Final-Testing/README.md) has the full web
  interface guide.

---

## Data

### Input documents (`Final-Testing/data/`)

| Folder | File | Role |
| --- | --- | --- |
| `authoritative/` | `ieee-constitution-and-bylaws.pdf` | IEEE Constitution and Bylaws (highest authority) |
| `authoritative/` | `SMC-Constitution-Bylaws-August-2023-web.pdf` | SMCS Constitution and Bylaws |
| `authoritative/` | `SMCS-Techncal-Manual-2023-08-01.pdf` | SMCS Technical Manual |
| `authoritative/` | `financial-ops-manual.pdf` | Financial Operations Manual (scanned; no text layer, see limitations) |
| `draft/` | `draft Operational Manual V5.pdf` | Draft operational manual (lower authority) |
| `derived/` | `SMCS_RAG_Derived_Governance_Test_Corpus.pdf` | Test corpus derived from the governance documents |
| `synthetic/` | `SMCS_RAG_Synthetic_Conflict_Stress_Test_Corpus.pdf` | Deliberately conflicting statements, to test conflict resolution |

The governance documents are public IEEE/SMCS documents. The derived and
synthetic corpora were created by the team for testing.

To add a document, put the PDF in the right folder and re-run
`python src\ingest.py`. Alternatively, upload a new version of a registered
document through the admin console.

### Generated data

| Path | Contents | In git? |
| --- | --- | --- |
| `chroma_db/` | Vector index built by `ingest.py` | No (rebuild with `ingest.py`) |
| `evaluation/golden_set.csv` | 50 questions with expected answer, keywords, source, page, abstention and conflict labels | Yes |
| `evaluation/evaluation_results_v2.csv`, `evaluation_summary_v2.json` | Latest per-question results and summary | Yes |
| `evaluation/evaluation_results.csv`, `evaluation_summary.json` | Earlier evaluation run | Yes |
| `*_test_results.json` | Results of the direct-factual and out-of-scope test scripts | Yes |
| `web/users.db` | User accounts (hashed passwords) | No (private) |
| `.admin_data/` | Admin releases, inventory, pending uploads, audit log | No (private) |

---

## Testing and evaluation

### Golden Set evaluation

```powershell
python evaluation\evaluate_rag.py
```

- The script runs all 50 Golden Set questions through `ask_question` and
  scores each one. It takes about 10 minutes.
- It overwrites `evaluation_results_v2.csv` and `evaluation_summary_v2.json`.
  Copy them first if you want to keep the previous results.

Results of the latest run (`evaluation_summary_v2.json`):

| Metric | Result |
| --- | --- |
| Questions (factual / conflict / out of scope) | 50 (25 / 15 / 10) |
| Answer accuracy | 96.0% |
| Factual answer accuracy | 100% |
| Conflict answer accuracy | 86.67% |
| Out-of-scope answer accuracy | 100% |
| Abstention accuracy | 100% (0 incorrect in-scope abstentions) |
| Retrieval source accuracy | 97.37% |
| Retrieval page accuracy | 93.55% |
| Citation source accuracy | 94.74% |
| Citation page accuracy | 74.19% |
| Conflict detection accuracy | 90.0% |
| Authority resolution accuracy | 91.67% |
| Full-pipeline pass rate (every check passes) | 76.0% |
| Average semantic similarity to expected answer | 0.82 |
| Total time | 548 s (about 11 s per question) |

### RAGAS (earlier version)

The results are in `tests/rag_evaluation_report.csv` on the `feat/admin-login`
branch; the notebooks are in `tests/`. This was a 20-question run on an earlier version of the pipeline:

| Metric | Result | Target |
| --- | --- | --- |
| Faithfulness | 0.629 | ≥ 0.90 |
| Answer relevancy | 0.726 | ≥ 0.85 |
| Context recall | 0.933 | – |

The low faithfulness led to the Semester 2 redesign. The redesign moved to
deterministic authority metadata, conflict rules and hybrid retrieval. RAGAS
has not been re-run on the final pipeline.

### Other test scripts (`Final-Testing/src/`)

| Script | Purpose |
| --- | --- |
| `test_retrieval.py` | Prints the top retrieved chunks for a query |
| `test_direct_factual.py` | Runs `20_Direct_Factual_Qs.json`; writes `direct_factual_test_results.json` |
| `test_out_of_scope.py` | Runs `out_of_scope_questions.json`; writes `out_of_scope_test_results.json` |

### Web application

The sign-in, web API and admin console were tested with automated scripts and
browser tests during development. Those test scripts are not part of the
repository; see Future work.

---

## Configuration

Set environment variables before starting the server. In PowerShell, for
example: `$env:RAG_ALLOW_SIGNUP="0"`.

| Variable | Default | Effect |
| --- | --- | --- |
| `PORT` | `8000` | Web server port |
| `RAG_PROJECT_DIR` | auto-detected | Folder containing `src/` (or `rag_chat.py`), `chroma_db/` and `data/` |
| `RAG_AUTH` | `1` | `0` turns sign-in off |
| `RAG_ALLOW_SIGNUP` | `1` | `0` hides **Create account** (accounts only via `auth.py add`) |
| `RAG_COOKIE_SECURE` | `0` | `1` makes the session cookie HTTPS-only (use behind HTTPS) |
| `RAG_USERS_DB` | `web/users.db` | Location of the accounts database |
| `RAG_DEMO_MODE` | `0` | `1` previews the interface with sample answers, without Ollama or the index |
| `ADMIN_ACCESS_TOKEN` | not set | Enables the admin console (32+ characters) |
| `ADMIN_STORAGE_DIR` | `.admin_data/` | Where admin releases and logs are stored |

Pipeline settings are constants at the top of `src/rag_chat.py`:
- retrieval sizes;
- `MAX_ACCEPTABLE_DISTANCE`;
- the embedding model.

Chunking settings are in `src/chunk_docs.py`. If you change the embedding
model or chunking, re-run `ingest.py`.

---

## Deployment

The target environment is a single computer, for example a society
office PC or a lab machine:
- it runs Ollama and the Python server;
- users connect with a browser at `http://<computer>:8000`.

Nothing else is needed: no cloud services and no external API keys.

**Sharing it temporarily.** A Cloudflare quick tunnel gives a temporary
public HTTPS address without opening firewall ports:

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

- Use `127.0.0.1`, not `localhost`.
- Set `$env:RAG_COOKIE_SECURE="1"` and `$env:RAG_ALLOW_SIGNUP="0"`, and
  create accounts with `auth.py`.
- The address changes every time the tunnel restarts, and the computer must
  stay on.

**Before a permanent deployment:**
- run the server behind a reverse proxy with HTTPS;
- use a fresh admin token;
- turn off self-sign-up;
- back up `web/users.db` and `.admin_data/`.

---

## Security and privacy

- **Local processing:** documents, questions and answers never leave the
  machine. There are no third-party LLM APIs.
- **Passwords:** stored only as salted PBKDF2-HMAC-SHA256 hashes
  (310,000 iterations). Session tokens are stored hashed.
- **Sessions:** HttpOnly, SameSite=Lax cookies, valid for 7 days.
- **Login lockout:** 5 failed attempts lock the username for 60 seconds.
- **Protected pages:** signed-in pages are not cached. PDFs are served only
  from the document folder and only to signed-in users.
- **Admin console:** protected by a bearer token and a Content-Security-Policy.
  Every change needs a reason and is written to the audit log.
- **Private data:** `users.db`, `.admin_data/` and `.env` files are
  git-ignored. Never commit them, or tokens, to the repository.
- **Conversation history:** kept in each user's browser, not on the server.

---

## Known issues and limitations

| Issue | Impact | Workaround / fix |
| --- | --- | --- |
| `financial-ops-manual.pdf` is a scanned image with no text layer | Its content cannot be searched or cited | Add OCR (e.g. Tesseract) during ingestion |
| Citation page accuracy is 74% | The right document is cited but sometimes a neighbouring page | Page-level re-ranking; smaller chunks |
| RAGAS faithfulness (0.63) was measured on an earlier version only | Faithfulness of the final pipeline is unmeasured | Re-run RAGAS on the final pipeline |
| Conflict detection is rule-based for 5 topics | New kinds of conflict are not detected automatically | Add rules, or a learned claim extractor |
| One question at a time | Concurrent users wait in line | Separate per-request state; multiple workers |
| About 11 s per answer on a typical PC | Slow on low-powered machines | GPU, or a smaller quantised model |
| Conversation history is stored in the browser | Not shared across devices | Store history on the server |
| One shared admin token | No individual admin accounts | Admin roles linked to user accounts |
| No email password reset or MFA | Password resets need the command line | Add email reset and MFA |
| Paths are relative to `Final-Testing` | Command-line scripts must run from that folder | Run commands from `Final-Testing` |
| An old commit contains a Hugging Face token in a deleted `.env.txt` | The token is visible in git history | Revoke the token; it is not used by the pipeline |

---

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `ollama` not found, or connection refused on port 11434 | Install Ollama and start it (`ollama serve`) |
| `model "llama3" not found` | `ollama pull llama3` |
| `Could not import chromadb` / missing packages | Activate the venv and start with `python web\server.py` (not `uvicorn`) |
| `cannot import name '_ExtendedAttributes'` | `python -m pip install -r requirements-lock.txt` |
| Every answer is "I cannot determine…" | `chroma_db/` is missing or empty, or you are in the wrong folder; run `python src\ingest.py` from `Final-Testing` |
| "The assistant is still loading" | Wait for `Pipeline ready` in the terminal |
| `/admin` says access is not configured | Set `ADMIN_ACCESS_TOKEN` before starting the server |
| "Too many failed attempts" | Wait 60 seconds |
| `Address already in use` | `$env:PORT="8001"; python web\server.py` |
| PowerShell will not run `activate` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

---

## Future work

1. **Coverage:**
   - add OCR to ingestion so scanned documents (the Financial Operations
     Manual) become searchable;
   - re-run RAGAS on the final pipeline.
2. **Answer quality:**
   - improve page-level citation accuracy, for example by page-level
     re-ranking or smaller, section-aware chunks;
   - extend conflict detection beyond the five rule-based topics, for
     example with an LLM- or NLI-based claim extractor checked against the
     Golden Set.
3. **Testing:**
   - add regression tests for the web server and admin console;
   - grow the Golden Set, and run the evaluation in CI.
4. **Scaling and accounts:**
   - support concurrent users (per-request pipeline state, multiple workers);
   - store conversation history on the server;
   - add individual admin accounts and roles, email password reset and MFA.
5. **Deployment:** containerise the system (Docker with Ollama) for one-step
   setup and deployment.

---

## Repository layout

```text
COMP6015-26S1-G13-RAGChatbot/
├── Final-Testing/                 ◄ DELIVERED SYSTEM
│   ├── src/
│   │   ├── parse_pdf.py           PDF parsing + authority metadata
│   │   ├── clean_text.py          text cleaning
│   │   ├── chunk_docs.py          chunking (1,500 / 200)
│   │   ├── embed_store.py         embeddings + ChromaDB helper
│   │   ├── ingest.py              builds chroma_db/ (run once)
│   │   ├── rag_chat.py            retrieval, abstention, answering, citations
│   │   ├── conflict_detection.py  rule-based conflict detection + authority
│   │   └── test_*.py              retrieval / factual / out-of-scope tests
│   ├── data/                      governance PDFs (authoritative, draft, derived, synthetic)
│   ├── evaluation/                Golden Set, evaluate_rag.py, results
│   ├── web/                       web server, sign-in, admin console, static pages
│   ├── docs/screenshots/          interface screenshots
│   ├── requirements.txt           direct dependencies
│   ├── requirements-lock.txt      exact tested versions
│   └── README.md                  detailed web interface guide
├── backend/                       earlier prototype: FastAPI backend and policy engine
├── frontend/                      earlier prototype: Next.js chat interface
├── tests/                         RAGAS notebooks (earlier version)
├── data/, chroma_db/              earlier prototype data and index
└── requirements.txt               earlier prototype dependencies
```

**Branches:**
- `main`: the delivered system.
- `feat/admin-login`, `feat/hybrid-semantic-rag`, `feature/*`, `develop`
  and `data-engineering`: development history.

---

## Team and acknowledgements

| Member | Role |
| --- | --- |
| Meet Rameshbhai Kalathiya | Data engineering: PDF parsing, chunking, vector database, retrieval pipeline, evaluation |
| Diya | AI and backend: RAG chain, prompt engineering, RAGAS evaluation |
| Jueun Yoo | Frontend prototype, policy engine, administrator console |

Individual contributions are detailed in the project report and the
requirements form.

**AI assistance:** the web interface, user sign-in, administrator-console
integration and parts of this documentation were developed with AI-assisted
coding (Claude Code). The administrator console's own handover notes also
record AI-assisted implementation.

**Third-party components:**
- [LangChain](https://www.langchain.com), [ChromaDB](https://www.trychroma.com),
  [Ollama](https://ollama.com) and Meta Llama 3;
- [BAAI bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5);
- [PyMuPDF](https://pymupdf.readthedocs.io), [FastAPI](https://fastapi.tiangolo.com)
  and [RAGAS](https://docs.ragas.io);
- IBM Plex fonts (SIL Open Font License).

The governance documents are published by IEEE and IEEE SMCS.
