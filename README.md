
# IEEE/SMCS Governance RAG Chatbot

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
| **Data Engineer** | Member 1 | PDF Parsing, Vector DB Management, Chunking A/B Testing |
| **AI & Backend** | Member 2 | RAG Chain Architecture, Prompt Engineering, RAGAS Evaluation |
| **Frontend & UI/UX** | June Yoo | Next.js Interface, Citation UI, API Integration |


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
├── src/
│   ├── ingestion/   # Parsing & Vectorization scripts
│   ├── retrieval/   # Search & Re-ranking logic
│   ├── generation/  # LLM Chains & System Prompts
│   └── frontend/    # Next.js Application
├── data/
│   ├── raw/         # Source PDF Corpus
│   └── golden-set/  # Ground Truth Dataset
└── tests/           # RAGAS & Rule-Sensitivity Tests
```

### 2. Installation
```bash
git clone https://github.com/rag-chatbot.git
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

## Ethics & Governance
* **Mandatory Citation:** Every claim must be traced back to a specific page and section.
* **Data Privacy:** Governance documents are processed in a local environment to prevent unauthorized data leakage.
* **Conflict Resolution:** In case of contradictory information, the system strictly follows the IEEE Hierarchy of Authority.

---
**[COMP6015] Group 13 - Master of Computing  Project**
