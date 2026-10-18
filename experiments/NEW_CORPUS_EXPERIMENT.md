# New PDF development experiment

Run from the repository root:

```bash
OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 ./venv/bin/python -m experiments.new_corpus_stress_test
OPENBLAS_NUM_THREADS=1 ./venv/bin/python -m experiments.review_new_corpus_results
./venv/bin/python -m unittest tests.test_policy_claims tests.test_authority_conflicts tests.test_vertical_slice tests.test_hybrid_rag tests.test_response_cache -q
```

The runner needs local `pdftoppm`, `tesseract` with English language data, and
the existing virtual environment. All computation is local. OCR is cached under
`experiment_outputs/new_corpus_20260908/ocr/`. Original PDFs are not modified.

## Experiment boundaries

- Financial manual: 27 scanned pages; OCR is required. Ten development queries
  use checked page/evidence anchors. This is retrieval evaluation, not financial advice.
- Derived governance corpus: only canonical summaries on pages 2–9 are indexed
  as background. Later expanded questions, reference answers and auditor notes
  are excluded. These summaries are not original governing documents.
- Synthetic stress corpus: 20 scenarios with baseline, conflicting and distractor
  records; expected labels and questions never enter the retrieval index.
- All documents are used in an isolated in-memory experiment adapter. No production
  registry entries or index files are added. Adapter authority scores (90/50) are
  controlled assumptions, not official rankings of the new documents.
- Compare five search modes and background chunk sizes 100/250/500 with 20% overlap.
  The A/B/C records stay atomic. This is not a full chunk-size sweep of every input.
- Record-pair Recall@5 measures the fraction of two specified record IDs returned.
  Pair hit@5 requires both IDs. Equivalent derived summaries do not count as exact
  source-record hits. MRR is truncated at 10; nDCG uses binary relevance.
- Oracle pair diagnostics bypass retrieval, with 20 positives each for cross-document,
  equal-authority and within-document variants plus 40 mechanical negative controls.
- Full chat checks call the real `RAGService.answer` in hybrid mode. No LLM generation
  is requested. Verified citations establish text existence, not correct reasoning.

## Interpreting improvements

The baseline snapshot is in `experiment_outputs/new_corpus_20260908_baseline/`;
the latest results, raw cases, SVG plots and code hashes are in
`experiment_outputs/new_corpus_20260908/`.

These cases were inspected during debugging and are now development/regression data.
Do not report the post-change scores as unseen test accuracy. A domain reviewer must
validate a separate final benchmark, including difficult non-conflicting examples.

New policy-claim matches are reported as potential conflicts requiring human review.
Matching quantities/terms alone does not establish a binding contradiction: subject,
scope, effective dates, approval and exceptions still need verification. The existing
deterministic hierarchy resolution remains for previously supported clear cases.

The financial PDF is readable by the experiment's OCR path; placing it in `RAG_data`
alone does not add OCR support or production retrieval approval to the application.

Keep generated OCR images and vector stores out of ordinary source-code commits.
