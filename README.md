# IEEE SMCS Authority-aware RAG Chatbot

This repository contains a working offline vertical slice of an authority-aware chatbot for IEEE SMCS documents. Chat is the primary product. Policy Audit and Golden Set evaluation are separate workflows.

The current generation mode is deterministic and extractive: it uses lexical section retrieval and returns sentences copied from retrieved evidence. It does not require an LLM key, does not call Ollama, and is labelled `deterministic_offline` in API/UI responses. It is useful as a leakage-safe baseline, not a claim of production semantic quality.

## Architecture

- `RAG_data/document_registry.json`: source-of-truth registry for approval, authority, usage, and retrieval eligibility.
- `backend/services/ingest_service.py`: PDF page extraction and section/clause-aware chunking into `backend/section_index.json`.
- `backend/services/search_service.py`: metadata-gated lexical retrieval and authority-aware reranking.
- `backend/services/rag_service.py`: extractive answers, citation validation, abstention, and conflict warnings.
- `backend/services/audit_service.py`: separate non-authoritative-clause audit against the Corrected Operations Manual.
- `backend/services/evaluation_service.py`: isolated Golden Set loader, predictor call, and post-prediction metrics.
- `backend/main.py`: validated FastAPI endpoints.
- `frontend/`: Next.js UI with Chat, Policy Audit, Documents, and Evaluation views.

Only records meeting all three rules enter chat retrieval: `usage=production`, `approval_status=approved`, and `retrieval_enabled=true`. The Old Manual, pending draft, Golden Set, corrected spreadsheet text, and Tom's comments never enter the chatbot index.

## Local setup

Python 3.11+ and Node.js 20+ are recommended.

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
npm install --prefix frontend
```

No model key is required for the implemented deterministic mode. Do not put secrets in the repository.

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
  -d '{"question":"What is the process for a Vice-President vacancy?"}'
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
  -d '{"query":"Vice President vacancy within 30 days"}'
```

The bounded response includes the query, candidate clause, lexical score, reranking score, inclusion/exclusion reason, page/section, approval/usage status, and authority level. Set `APP_ENV=production` to remove this endpoint from OpenAPI and return HTTP 404.

## Tests, lint, and build

```bash
./venv/bin/python -m unittest tests.test_vertical_slice -v
npm test --prefix frontend
npm run lint --prefix frontend
npm run build --prefix frontend
```

## API summary

- `GET /api/health`
- `GET /api/documents`
- `POST /api/chat`
- `POST /api/audit`
- `POST /api/evaluation/run`
- `POST /ask` (legacy compatibility)

Production PDFs are served only from `/documents/corpus`; evaluation and pending folders are not mounted.

## Known metadata and evaluation limitations

- The request named the Corrected Operations Manual as the highest authority, so its registry level is `100`. This intentionally overrides the hierarchy described inside that manual and should be confirmed by the project owner.
- Approval status and effective dates were inferred from the supplied brief and filenames. They require manual governance verification before production use.
- The workbook itself says it is an expert-annotated candidate set, not a fully validated final benchmark; G014 and Word-derived section/page references need manual verification.
- Only two scored rows currently have `Expected Issue = no_issue`, so false-positive rate is reported but labelled unreliable.
- Three additional exact-copy, authority-supported negative clauses are regression-tested, but are not added to the official Golden Set denominator. The warning remains until experts approve more benchmark negatives.
- Conflict classification and correction suggestions are deterministic baseline heuristics. There is no keyed LLM generator, semantic embedding model, or claim-level natural-language inference in this version.
- The existing Chroma database was preserved but not reused because it contains legacy metadata from deleted `data/` paths and cannot prove the required usage boundary. The new JSON index is rebuildable and auditable.

No deployment or production/staging changes are performed by these commands.
