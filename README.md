# IEEE SMCS Authority-aware RAG Chatbot

This repository contains an authority-aware hybrid RAG chatbot for IEEE SMCS documents. Chat is the primary product. Policy Audit and Golden Set evaluation are separate workflows.

Three modes preserve the verified baseline while allowing controlled comparison:

- `deterministic`: the committed lexical, extractive offline baseline.
- `hybrid`: lexical retrieval fused with local latent-semantic embeddings, reranking, and deduplication; no LLM.
- `hybrid_llm`: hybrid retrieval followed by optional evidence-only synthesis. Without `OPENAI_API_KEY`, or when generated citations fail validation, it safely returns the hybrid non-LLM answer and reports the fallback.

Development experiments also expose three clean retrieval ablations: `bm25`
(probabilistic lexical ranking), `dense` (embedding similarity only), and `rrf`
(Reciprocal Rank Fusion of the independent BM25 and dense rankings). The comparison
endpoint evaluates `deterministic`, `bm25`, `dense`, and `rrf` without changing the
downstream audit classifier.

## Architecture

- `RAG_data/document_registry.json`: source-of-truth registry for approval, authority, usage, and retrieval eligibility.
- `backend/services/ingest_service.py`: PDF page extraction and section/clause-aware chunking into `backend/section_index.json`.
- `backend/services/embedding_service.py`: reproducible local 128-dimensional LSA embeddings, with an explicitly configurable local sentence-transformer option.
- `backend/services/search_service.py`: metadata-gated lexical/vector fusion, reranking, and semantic deduplication.
- `backend/services/llm_service.py`: optional evidence-only synthesis; it receives retrieved production citations, never evaluation rows.
- `backend/services/rag_service.py`: extractive answers, citation validation, abstention, and conflict warnings.
- `backend/services/audit_service.py`: separate non-authoritative-clause audit against the Corrected Operations Manual.
- `backend/services/evaluation_service.py`: isolated Golden Set loader, predictor call, and post-prediction metrics.
- `backend/main.py`: validated FastAPI endpoints.
- `frontend/`: Next.js UI with Chat, Policy Audit, Documents, and Evaluation views.

Only records meeting all three rules enter chat retrieval: `usage=production`, `approval_status=approved`, and `retrieval_enabled=true`. The Old Manual, pending draft, Golden Set, corrected spreadsheet text, and Tom's comments never enter the chatbot index.

The supervisor-confirmed hierarchy is applied to final conflict reasoning, not only ranking:

1. IEEE Constitution and Bylaws — authority `100`
2. SMCS Constitution and Bylaws — authority `90`
3. Corrected Operations Manual — authority `80`
4. SMCS Technical Manual — authority `70`

Cross-document conflicts retain and cite both passages while the higher-authority passage governs. Conflicting clauses within the same document are returned as an unresolved internal ambiguity: the system identifies normative terms, presents both interpretations, requires human review, and abstains from selecting a definitive rule.

## Local setup

Python 3.11+ and Node.js 20+ are recommended.

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
npm install --prefix frontend
```

No model key is required for deterministic or hybrid mode. Optional OpenAI synthesis reads `OPENAI_API_KEY` from the process environment; do not put secrets in the repository. Configuration defaults are:

```text
EMBEDDING_BACKEND=local_lsa
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2  # used only with EMBEDDING_BACKEND=sentence_transformer
LLM_PROVIDER=openai
LLM_MODEL=gpt-4.1-mini
CORS_ORIGINS=http://localhost:3000
# Evaluation endpoints default off when APP_ENV=production
ENABLE_EVALUATION_API=true
CHAT_CACHE_TTL_SECONDS=300
CHAT_CACHE_MAX_ENTRIES=256
```

To use the locally installed Ollama embedding and generation models in the main app:

```bash
export EMBEDDING_BACKEND=ollama
export EMBEDDING_MODEL=nomic-embed-text:latest
export LLM_PROVIDER=ollama
export LLM_MODEL=llama3.1:8b
export OLLAMA_BASE_URL=http://127.0.0.1:11434
./venv/bin/python -m uvicorn backend.main:app --reload
```

The first startup embeds the section index in local Ollama batches. Later requests in the same backend process reuse the in-memory document vectors.

## Register and ingest documents

1. Place a source under the appropriate `RAG_data/` folder.
2. Add its complete metadata to `RAG_data/document_registry.json`.
3. For production retrieval, explicitly set `usage` to `production`, `approval_status` to `approved`, and `retrieval_enabled` to `true`.
4. Rebuild the index:

```bash
./venv/bin/python -m backend.scripts.run_ingest
```

The command reports the real number of indexed sections/pages. Non-production registry records are filtered before PDF parsing.

## Start backend and frontend

Terminal 1:

```bash
./venv/bin/python -m uvicorn backend.main:app --reload --port 8000
```

Terminal 2:

```bash
npm run dev --prefix frontend
```

Open `http://localhost:3000`. To use another API origin, set `NEXT_PUBLIC_API_URL` before starting Next.js.

## Ask one chatbot question

```bash
curl -s http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the process for a Vice-President vacancy?","mode":"hybrid"}'
```

The response includes structured citations, confidence, conflict status, and abstention fields.

In deterministic mode the chatbot returns one directly supported passage, removes semantically duplicate evidence, and does not concatenate unrelated retrieval results. Process questions may include adjacent sentences only when they come from the same retrieved clause. Incomplete headings/fragments are rejected. Section/article labels are copied from parsed document headings; when a continuation page has no reliable heading, the section is returned as `null` rather than using a chunk ID.

## Run one policy audit

```bash
curl -s http://localhost:8000/api/audit \
  -H 'Content-Type: application/json' \
  -d '{"document_id":"smcs-operations-manual-v2-old","text":"Within-term vacancies of a Vice President shall be filled from two candidates with biographies."}'
```

Or run it without the server:

```bash
./venv/bin/python -m backend.scripts.run_audit \
  --document-id smcs-operations-manual-v2-old \
  'Within-term vacancies of a Vice President shall be filled from two candidates with biographies.'
```

Audit retrieves authoritative evidence before deciding. A whole document is not silently audited; the caller must supply the selected clause.

## Run Golden Set evaluation

```bash
./venv/bin/python -m backend.scripts.run_evaluation
```

Or with the backend running:

```bash
curl -s -X POST http://localhost:8000/api/evaluation/run
```

Compare all three modes on the same development cases:

```bash
curl -s -X POST http://localhost:8000/api/evaluation/compare
```

Run the separate 50-case holdout benchmark (25 issue and 25 no-issue cases):

```bash
./venv/bin/python -m backend.scripts.run_evaluation \
  --dataset tests/holdout_audit_set.json --summary
```

Keep this holdout file separate from rule and threshold tuning. If a case is used
to design a fix, move it into the development/regression set and replace it with
a newly reviewed holdout case before reporting final generalisation metrics.

The comparison includes retrieval recall@5, mean reciprocal rank, nDCG@10, detection recall, confusion counts, issue-type and citation accuracy, abstentions, average measured latency, and per-case results. These 12 cases are a repeatedly inspected development benchmark, not an unseen final test set. LLM synthesis remains limited to chatbot answers.

Only `Include in Scoring = Yes` rows are evaluated. Prediction receives only `Gold ID` and `Old Manual Text`; corrected text, Tom's comments, expected labels, explanations, and actions are accessed only after prediction for scoring. The report includes per-case results and clearly warns when the no-issue sample is too small for a reliable false-positive rate.

The evaluation response exposes the complete confusion matrix and denominators:

- `total scored = positive cases + negative/no-issue cases`
- `positive cases = true positives + false negatives`
- `negative cases = true negatives + false positives`
- `detection recall = true positives / positive cases`
- `false-positive rate = false positives / negative cases`
- `issue-type accuracy = exact broad Expected Issue matches / total scored cases`; abstentions count as incorrect.
- `citation accuracy = non-abstained cases with a validated Corrected Operations Manual citation / non-abstained cases`.
- `correction accuracy = positive cases whose suggestion covers at least 35% of normalized Expected Action tokens / positive cases`.

The broad `Expected Issue` column is compared with `issue_type`; `Issue Subtype` is reported separately and is not sent to prediction. This fixes the earlier field/label mismatch that forced issue-type accuracy to 0%.

## Development-only retrieval debugging

With the default `APP_ENV=development`, inspect candidate clauses and filtering/ranking decisions:

```bash
curl -s http://localhost:8000/api/debug/retrieval \
  -H 'Content-Type: application/json' \
  -d '{"query":"Vice President vacancy within 30 days","mode":"hybrid"}'
```

The bounded response includes the query, candidate clause, lexical, vector, hybrid and reranking scores, inclusion/exclusion reason, page/section, approval/usage status, and authority level. Set `APP_ENV=production` to remove this endpoint from OpenAPI and return HTTP 404. The mode selector in the UI is also shown only when the health endpoint reports development mode.

## Tests, lint, and build

```bash
./venv/bin/python -m unittest tests.test_authority_conflicts tests.test_vertical_slice tests.test_hybrid_rag -v
npm test --prefix frontend
npm run lint --prefix frontend
npm run build --prefix frontend
```

## API summary

- `GET /api/health`
- `GET /api/health/live`
- `GET /api/health/ready`
- `GET /api/documents`
- `POST /api/chat`
- `POST /api/audit`
- `POST /api/evaluation/run`
- `POST /api/evaluation/compare`
- `POST /api/debug/retrieval` (development only)
- `POST /ask` (legacy compatibility)

Production PDFs are served only from `/documents/corpus`; evaluation and pending folders are not mounted.

## Known metadata and evaluation limitations

- The supervisor-confirmed hierarchy places IEEE Constitution and Bylaws first, followed by SMCS Constitution and Bylaws, the Corrected Operations Manual, and the SMCS Technical Manual. Registry scores and conflict reasoning use this order.
- Approval status and effective dates were inferred from the supplied brief and filenames. They require manual governance verification before production use.
- The workbook itself says it is an expert-annotated candidate set, not a fully validated final benchmark; G014 and Word-derived section/page references need manual verification.
- The original development workbook has only two scored `no_issue` rows, so its false-positive rate is labelled unreliable. The separate holdout has 25 `no_issue` rows and must not be used for iterative threshold tuning.
- Three additional exact-copy, authority-supported negative clauses are regression-tested, but are not added to the official Golden Set denominator. The warning remains until experts approve more benchmark negatives.
- Conflict classification and correction suggestions remain deterministic heuristics. Hybrid retrieval improves candidate discovery but does not itself provide claim-level inference.
- Local LSA embeddings are reproducible and offline, but weaker than a domain-tuned transformer. Set `EMBEDDING_BACKEND=sentence_transformer` only when the configured model is already installed locally; the service does not silently download models.
- LLM output is optional and citation-gated, but citation validation proves that quoted evidence exists—not that every generated paraphrase is logically entailed. Human review remains necessary.
- The existing Chroma database was preserved but not reused because it contains legacy metadata from deleted `data/` paths and cannot prove the required usage boundary. The new JSON index is rebuildable and auditable.

No deployment or production/staging changes are performed by these commands.
