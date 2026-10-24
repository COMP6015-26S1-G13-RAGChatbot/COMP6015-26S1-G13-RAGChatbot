
# IEEE/SMCS Governance RAG Chatbot

> **Final version:** the delivered system is in [`Final-Testing/`](Final-Testing/README.md):
> the RAG pipeline (`src/`, local Llama 3 via Ollama, BGE embeddings, ChromaDB),
> the governance PDFs (`data/`), the 50-question evaluation (`evaluation/`), and the
> web interface with user sign-in and administrator console (`web/`).
> Setup and run instructions are in [`Final-Testing/README.md`](Final-Testing/README.md).
> The sections below describe the original project plan; `backend/`, `frontend/` and
> `tests/` contain earlier prototypes and the RAGAS notebooks.

> **Target:** Human-Level Reliability (HLR) $\ge$ 90%  
> **Methodology:** Iterative Prototyping within an Agile Framework

This project is a high-performance RAG (Retrieval-Augmented Generation) chatbot designed to provide precise information based on IEEE and SMCS governance documents (Bylaws, Operations Manuals, etc.). It features **page-level citations** for every response to ensure maximum transparency and auditability.

## Project Overview
The system is engineered to accurately parse complex IEEE 2-column layouts and minimize hallucinations by adhering to a strict **Hierarchy of Authority** between documents. We utilize the **RAGAS framework** for continuous performance benchmarking and optimization.

### Tech Stack
* **Orchestration:** Python, LangChain
* **LLM:** Gemini 1.5 Pro / GPT-4o (Benchmarked)
* **Vector DB:** ChromaDB (Local Deployment for Data Governance)
* **Frontend:** Next.js, Tailwind CSS
* **Evaluation:** RAGAS Framework

## System Architecture
The pipeline is structured across three functional layers:

### 1. Ingestion Layer
* **Layout-aware Parsing:** PDF-to-Markdown conversion preserving structural integrity.
* **Recursive Chunking:** 512-token chunks with 50-token overlap.
* **Metadata Tagging:** Detailed indexing by Document, Page, Section, and Version.

### 2. Retrieval Layer
* **Stage 1 (Vector Search):** Cosine similarity search (Default $k=10$) for high recall.
* **Stage 2 (Re-ranking):** Cross-encoder model to refine precision (Default $n=5$).

### 3. Generation Layer
* **Constrained Generation:** System prompts restricted to retrieved context only.
* **Hierarchy Logic:** Priority-based resolution (Main Bylaws > SMCS Bylaws > Ops Manual).
* **Tracer Logic:** Automated citation mapping to source metadata.

## Team Roles & Responsibilities

| Role | Member | Key Focus |
| :--- | :--- | :--- |
| **Data Engineer** | MEET | PDF Parsing, Vector DB Management, Chunking A/B Testing |
| **AI & Backend** | DIYA | RAG Chain Architecture, Prompt Engineering, RAGAS Evaluation |
| **Frontend & UI/UX** | June  | Next.js Interface, Citation UI, API Integration |


## Evaluation Framework (The Golden Set)
Performance is measured at each iteration using a manually curated **Golden Set** of 50 verified Q&A pairs.

| Metric | Formula | Target | Diagnosis |
| :--- | :--- | :--- | :--- |
| **Faithfulness** | $C_{supported} / C_{total}$ | $\ge$ 0.90 | Hallucination Control |
| **Answer Relevance** | $Avg. cos(q, g)$ | $\ge$ 0.85 | Retrieval & Chunking Quality |
| **Citation Accuracy** | $(R_{correct} / R_{total}) \times 100$ | 100% | Tracer Logic Integrity |
| **HLR** | $(Agreements / Total) \times 100$ | $\ge$ 90% | Production Readiness |

---

## Getting Started

### 1. Repository Structure
```text
├── data/
│   ├── raw/                # Source PDFs (IEEE Bylaws, SMCS, etc.)
│   ├── processed/          # Markdown-converted files (MEET)
│   └── golden-set.json     # 50 Q&A Ground Truth Dataset (Section 4.4.1)
├── src/
│   ├── ingestion/          # MEET : Layout-aware Parsing & Chunking A/B Tests
│   ├── retrieval/          # DIYA: Vector Search & Cross-encoder Re-ranking
│   ├── generation/         # DIYA: LangChain, Hierarchy Logic & Citation Tracer
│   └── frontend/           # JUNE: Next.js & Tailwind (Perplexity-style UI)
├── tests/
│   ├── ragas_eval.py       # Automated RAGAS Metrics (Formulas 1-4)
│   └── rule_sensitivity.py # Rule-Sensitivity & Update Latency Tests (Formulas 5-6)
├── .gitignore              # Environment keys (.env) and local data exclusions
└── README.md               # Project overview and HLR target metrics
```

### 2. Installation
```bash
git clone https://github.com/COMP6015-26S1-G13-RAGChatbot/COMP6015-26S1-G13-RAGChatbot.git
cd rag-chatbot
pip install -r requirements.txt
npm install --prefix src/frontend
```

### 3. Environment Variables
Create a `.env` file with the following configurations:
* `GOOGLE_API_KEY` (For Gemini 1.5 Pro)
* `OPENAI_API_KEY` (For Embeddings)
* `DATABASE_URL` (For ChromaDB/Supabase)

---
### 4. Running the Application

#### Backend (FastAPI)
To run the FastAPI backend, you need to add the backend directory to your `PYTHONPATH` so that modules can be resolved correctly. Run the following commands from the project root:

```bash
# 1. Activate your virtual environment (if not already done)
source venv/bin/activate  # On Windows use: venv\Scripts\activate

# 2. Set PYTHONPATH and start the Uvicorn server
export PYTHONPATH=$PYTHONPATH:$(pwd)/backend
uvicorn backend.main:app --reload

```


## Ethics & Governance
* **Mandatory Citation:** Every claim must be traced back to a specific page and section.
* **Data Privacy:** Governance documents are processed in a local environment to prevent unauthorized data leakage.
* **Conflict Resolution:** In case of contradictory information, the system strictly follows the IEEE Hierarchy of Authority.

---
**[COMP6015] Group 13 - Master of Computing  Project**
