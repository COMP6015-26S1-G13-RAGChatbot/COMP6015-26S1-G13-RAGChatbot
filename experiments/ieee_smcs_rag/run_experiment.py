from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict
from pathlib import Path

from experiments.ieee_smcs_rag.pipeline import (
    CorpusLoader, OllamaGateway, VectorExperiment, deterministic_scope,
    load_golden_rows, simple_bar_chart, tokens, write_csv,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "experiment_outputs" / "ieee_smcs_rag"
AUTHORITY = {
    "IEEE Constitution and Bylaws": 100,
    "SMCS Constitution and Bylaws": 90,
    "Corrected Operations Manual": 80,
    "SMCS Technical Manual": 70,
}


def overlap(reference: str, candidate: str) -> float:
    expected = set(tokens(reference))
    actual = set(tokens(candidate))
    return len(expected & actual) / max(1, len(expected))


def correction_match(suggestion: str | None, expected: str) -> bool:
    return bool(suggestion and expected and overlap(expected, suggestion) >= .35)


def validate_registry(documents) -> None:
    actual = {doc.name: doc.authority_score for doc in documents if doc.usage == "production"}
    if actual != AUTHORITY:
        raise RuntimeError(f"Authority hierarchy mismatch: {actual}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the IEEE SMCS Ollama RAG experiment")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--base-url", default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    parser.add_argument("--embedding-model", default=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest"))
    parser.add_argument("--models", nargs="+", default=[os.getenv("OLLAMA_MODEL", "llama3:latest")])
    parser.add_argument("--chunk-sizes", nargs="+", type=int, default=[300, 600, 1000])
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    loader = CorpusLoader(ROOT)
    documents = loader.documents()
    validate_registry(documents)
    supported = [doc for doc in documents if Path(doc.path).suffix.lower() in {".pdf", ".docx", ".txt"}]
    inventory = []
    loaded_by_id = {}
    for doc in supported:
        units = loader.load(doc)
        loaded_by_id[doc.document_id] = units
        inventory.append({"document_id": doc.document_id, "document": doc.name,
                          "format": Path(doc.path).suffix.lower().lstrip("."), "units": len(units),
                          "usage": doc.usage, "approval": doc.approval_status,
                          "retrieval_enabled": doc.retrieval_enabled, "indexed": bool(
                              doc.usage == "production" and doc.approval_status == "approved" and doc.retrieval_enabled)})
    write_csv(OUTPUT / "document_inventory.csv", inventory)

    gateway = OllamaGateway(args.base_url, args.embedding_model, args.models[0])
    installed = gateway.installed_models()
    required = {args.embedding_model, *args.models}
    missing = required - installed
    if missing:
        raise RuntimeError(f"Requested Ollama models are not installed: {sorted(missing)}")

    golden = [row for row in load_golden_rows(ROOT / "RAG_data" / "COMP6016_Operations_Manual_Golden_Set.xlsx")
              if row.get("Include in Scoring", "").strip().lower() == "yes"]
    if args.smoke:
        golden = golden[:1]
        args.chunk_sizes = [600]

    retrieval_rows = []
    stores = {}
    production = [doc for doc in documents if doc.usage == "production" and
                  doc.approval_status == "approved" and doc.retrieval_enabled]
    for chunk_size in args.chunk_sizes:
        chunks = [chunk for doc in production for chunk in loader.chunk(doc, loaded_by_id[doc.document_id], chunk_size)]
        if any(chunk.usage != "production" or chunk.approval_status != "approved" for chunk in chunks):
            raise RuntimeError("Non-production chunk crossed the retrieval boundary")
        store = VectorExperiment(chunks, gateway, OUTPUT, f"smcs_{chunk_size}")
        stores[chunk_size] = store
        for method in ("keyword", "dense", "hybrid"):
            latencies, hits_count = [], 0
            for row in golden:
                started = time.perf_counter()
                hits = store.retrieve(row["Old Manual Text"], method, k=5)
                latencies.append((time.perf_counter() - started) * 1000)
                # Ground truth is joined after retrieval and is never used as a query or prompt.
                relevance = max((overlap(row["Corrected Manual Text"], hit.chunk.text) for hit in hits), default=0)
                hits_count += relevance >= .25
            retrieval_rows.append({
                "chunk_size_words": chunk_size, "retrieval_method": method,
                "cases": len(golden), "retrieval_recall_at_5": hits_count / max(1, len(golden)),
                "average_retrieval_latency_ms": sum(latencies) / max(1, len(latencies)),
                "chunks": len(chunks), "embedding_model": args.embedding_model,
            })
    write_csv(OUTPUT / ("smoke_retrieval.csv" if args.smoke else "retrieval_grid.csv"), retrieval_rows)
    best = max(retrieval_rows, key=lambda row: (row["retrieval_recall_at_5"], -row["average_retrieval_latency_ms"]))
    store = stores[int(best["chunk_size_words"])]
    method = str(best["retrieval_method"])

    case_rows = []
    for model in args.models:
        gateway.generation_model = model
        for row in golden:
            question = ("Audit this non-authoritative policy clause against the approved production documents. "
                        "Identify whether it contains a conflict, unsupported claim, missing requirement, ambiguity, or no issue.\n\n"
                        + row["Old Manual Text"])
            hits = store.retrieve(question, method, k=5)
            scope, deterministic = deterministic_scope(question, hits)
            result = gateway.synthesize(question, hits, scope, deterministic)
            valid_ids = {hit.chunk.chunk_id for hit in hits}
            citations_valid = bool(result.citation_ids) and set(result.citation_ids) <= valid_ids
            expected = row["Expected Issue"].strip()
            expected_positive = expected != "no_issue"
            predicted_positive = result.issue_type != "no_issue"
            case_rows.append({
                "gold_id": row["Gold ID"], "model": model,
                "chunk_size_words": best["chunk_size_words"], "retrieval_method": method,
                "expected_issue": expected, "predicted_issue": result.issue_type,
                "expected_positive": expected_positive, "predicted_positive": predicted_positive,
                "retrieval_hit": max((overlap(row["Corrected Manual Text"], hit.chunk.text) for hit in hits), default=0) >= .25,
                "citation_valid": citations_valid, "correction_correct": correction_match(result.suggested_correction, row["Expected Action"]),
                "abstained": result.abstained, "llm_called": result.llm_called,
                "fallback_used": result.fallback_used, "fallback_reason": result.fallback_reason,
                "latency_ms": result.latency_ms, "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens, "citation_ids": "|".join(result.citation_ids),
                "answer": result.answer.replace("\n", " "),
            })
    write_csv(OUTPUT / ("smoke_cases.csv" if args.smoke else "ollama_cases.csv"), case_rows)

    summaries = []
    for model in args.models:
        cases = [row for row in case_rows if row["model"] == model]
        positives = [row for row in cases if row["expected_positive"]]
        negatives = [row for row in cases if not row["expected_positive"]]
        tp = sum(row["expected_positive"] and row["predicted_positive"] for row in cases)
        fp = sum(not row["expected_positive"] and row["predicted_positive"] for row in cases)
        summaries.append({
            "model": model, "cases": len(cases), "chunk_size_words": best["chunk_size_words"],
            "retrieval_method": method, "retrieval_recall_at_5": sum(row["retrieval_hit"] for row in cases) / max(1, len(cases)),
            "detection_recall": tp / max(1, len(positives)), "false_positive_rate": fp / max(1, len(negatives)),
            "issue_type_accuracy": sum(row["expected_issue"] == row["predicted_issue"] for row in cases) / max(1, len(cases)),
            "correction_accuracy": sum(row["correction_correct"] for row in positives) / max(1, len(positives)),
            "citation_accuracy": sum(row["citation_valid"] for row in cases) / max(1, len(cases)),
            "abstentions": sum(row["abstained"] for row in cases),
            "average_latency_ms": sum(float(row["latency_ms"]) for row in cases) / max(1, len(cases)),
            "llm_called_cases": sum(row["llm_called"] for row in cases),
            "fallback_cases": sum(row["fallback_used"] for row in cases),
        })
    write_csv(OUTPUT / ("smoke_summary.csv" if args.smoke else "ollama_summary.csv"), summaries)

    if not args.smoke:
        simple_bar_chart(OUTPUT / "retrieval_comparison.svg", "Retrieval recall@5",
                         [f"{r['chunk_size_words']}/{r['retrieval_method']}" for r in retrieval_rows],
                         [float(r["retrieval_recall_at_5"]) for r in retrieval_rows])
        simple_bar_chart(OUTPUT / "ollama_metrics.svg", "Ollama evaluation metrics",
                         ["retrieval", "detection", "FPR", "issue type", "correction", "citation"],
                         [float(summaries[0][key]) for key in ("retrieval_recall_at_5", "detection_recall", "false_positive_rate",
                                                               "issue_type_accuracy", "correction_accuracy", "citation_accuracy")])
        report = f"""# IEEE SMCS RAG experiment

## Scope and data boundaries

- Real registered PDF/DOCX/TXT files were inventoried and parsed. Only approved, retrieval-enabled production documents were indexed.
- No TXT document exists in the supplied corpus; TXT loading is implemented but had zero real inputs.
- The referenced attached Python file was not present in the attachment store, so the runnable experiment was rebuilt from the repository implementation.
- Golden Set prediction received only `Old Manual Text`. Expected labels, corrected text, comments, actions, and explanations were used only after prediction for scoring.
- Authority is enforced by application metadata: IEEE Constitution and Bylaws 100; SMCS Constitution and Bylaws 90; Corrected Operations Manual 80; SMCS Technical Manual 70.

## Configuration

- Ollama URL: `{args.base_url}`
- Embedding model: `{args.embedding_model}`
- Generation models actually tested: {', '.join(args.models)}
- Chunk sizes: {', '.join(map(str, args.chunk_sizes))} words
- Retrieval methods: keyword, dense, hybrid
- Best retrieval configuration: `{best['chunk_size_words']}` words / `{method}`

## Results

```json
{json.dumps(summaries, indent=2)}
```

The two negative cases remain too few for a reliable false-positive-rate estimate. Citation accuracy validates that every returned ID belongs to the supplied retrieved evidence; it does not prove that every paraphrase is logically entailed. This is a development benchmark, not an unseen final test set.
"""
        (OUTPUT / "REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({"smoke": args.smoke, "installed_models": sorted(installed), "best": best,
                      "summary": summaries, "output_dir": str(OUTPUT)}, indent=2))
    return 0 if all(not row["fallback_used"] and row["citation_valid"] for row in case_rows) else 2


if __name__ == "__main__":
    raise SystemExit(main())
