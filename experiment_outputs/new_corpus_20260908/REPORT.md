# New corpus development stress test

No production registry/index was modified. No LLM or remote API was called.
Synthetic PDF: 20 scenarios; 60 policy records. Labels, golden questions and expected-behaviour text excluded from retrieval.
Record A/B are the strict relevant pair. Derived summaries and OCR financial pages act as additional distractors; semantically equivalent summaries are not scored as exact evidence hits.
Authority 90/50 is an in-memory controlled assumption, not verified official status. Draft cases 17/18 require status review; no claim of valid real-policy resolution is made.
Chunk sweep changes background document chunks only; atomic A/B/C records are preserved. No source-reference verification or final held-out generalisation claim.
Latency is one local retrieval call per query/config, excluding index construction, OCR and generation; query caches cleared. Not directly comparable with old answer latency.

| Words | Chunks | Method | Recall@5 | Pair hit@5 | MRR@10 | nDCG@10 | ms | Target conflict recall |
|---:|---:|---|---:|---:|---:|---:|---:|---:|
|100|245|deterministic|0.675|0.500|0.370|0.478|49.9|0.500|
|100|245|bm25|0.550|0.300|0.365|0.477|46.6|0.300|
|100|245|dense|0.675|0.450|0.788|0.658|45.5|0.450|
|100|245|rrf|0.725|0.550|0.659|0.624|45.9|0.550|
|100|245|hybrid|0.750|0.600|0.659|0.636|67.5|0.550|
|250|146|deterministic|0.550|0.350|0.357|0.455|56.3|0.350|
|250|146|bm25|0.550|0.300|0.375|0.495|58.0|0.300|
|250|146|dense|0.550|0.200|0.517|0.488|47.7|0.200|
|250|146|rrf|0.650|0.400|0.503|0.556|50.0|0.400|
|250|146|hybrid|0.625|0.350|0.487|0.540|61.9|0.350|
|500|112|deterministic|0.525|0.300|0.365|0.440|64.1|0.300|
|500|112|bm25|0.650|0.500|0.429|0.552|55.5|0.500|
|500|112|dense|0.625|0.300|0.456|0.473|41.3|0.300|
|500|112|rrf|0.750|0.600|0.461|0.570|45.4|0.600|
|500|112|hybrid|0.675|0.500|0.401|0.533|74.2|0.500|

## Oracle pair diagnostic (retrieval bypassed)

| Variant | Detected | Cases | Human review |
|---|---:|---:|---:|
|cross_document|17|20|17|
|equal_authority|17|20|17|
|within_document|17|20|17|
|no_issue_distractor|0|20|0|
|no_issue_identical|0|20|0|

## Financial OCR retrieval (10 manually constructed development questions)
A hit requires the expected financial PDF page AND an evidence anchor in the returned chunk. This does not prove the whole answer is complete.

| Words | Method | Evidence hit@5 | MRR@10 |
|---:|---|---:|---:|
|100|deterministic|1.000|0.867|
|100|bm25|1.000|0.933|
|100|dense|0.900|0.842|
|100|rrf|1.000|0.850|
|100|hybrid|1.000|0.933|
|250|deterministic|1.000|0.883|
|250|bm25|1.000|0.883|
|250|dense|1.000|0.850|
|250|rrf|1.000|0.867|
|250|hybrid|1.000|0.933|
|500|deterministic|1.000|0.900|
|500|bm25|1.000|0.883|
|500|dense|1.000|0.858|
|500|rrf|1.000|0.883|
|500|hybrid|1.000|0.900|

Within-document controls relocate contradictory records into one virtual document; this is a constructed test, not a claim that the source PDF contains official contradictions.
No-issue controls are mechanical diagnostics, not an expert-validated specificity benchmark.
The conflict stage uses the application pair detector over retrieved full passages. It does not measure final LLM answer correctness or complete chat/audit API behaviour.

## Failure review

- Scenario 09: President-Elect eligibility — missed even with both passages supplied.
- Scenario 15: New TC approval — missed even with both passages supplied.
- Scenario 16: Annual conference sponsorship — missed even with both passages supplied.

## Full chat service check

20 scenario queries were additionally passed through RAGService.answer in hybrid mode, with 100-word background chunks. No LLM generation was requested. This checks answer/citation/abstention behaviour separately from the top-5 full-passage pair experiment.

- Exact target conflict detected: 13/20.
- Any conflict reported: 14/20.
- Nonempty source-text-verified citations: 20/20.
- Abstained: 14/20.

Citation verification checks text existence, not logical correctness or authoritative status. Synthetic records remain experiment-only, even though the isolated adapter permits them for diagnostic retrieval.

## Changes and limitations

Added quantity/unit normalisation, voting-threshold and permission/obligation candidate detection, subject/condition guards, neutral-question internal conflict detection and bounded counterpart search. New heuristic matches and draft/status-uncertain pairs require human review, not automatic policy resolution. Embedding query caches now include corpus identity.

These 20 inspected scenarios are development regression data, not an unseen final benchmark. The detector remains rule-based and does not cover arbitrary logical implications or all exceptions. Source-derived paraphrases are not verified original policies. The financial manual was OCRed for this experiment only; the production ingestion service still needs an explicit OCR workflow. Neither generation quality nor real-document contradiction ground truth is established by this test.
