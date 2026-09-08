import re
import time
import zipfile
import json
import math
from pathlib import Path
from xml.etree import ElementTree as ET

from backend.core.config import Config
from backend.models import ComparisonResponse, EvaluationCase, EvaluationResponse, RAGMode
from backend.services.llm_service import GroundedLLMService
from backend.services.audit_service import AuditService
from backend.services.search_service import semantic_similarity, tokens


NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def _column_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference).group(0)
    result = 0
    for letter in letters:
        result = result * 26 + ord(letter) - 64
    return result - 1


def load_golden_rows(path=Config.GOLDEN_SET_PATH) -> list[dict[str, str]]:
    """Read the Golden Set worksheet without making it available to retrieval or prediction."""
    with zipfile.ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(node.text or "" for node in item.findall(".//x:t", NS))
                       for item in root.findall("x:si", NS)]
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rel_id = next(sheet.attrib[f"{{{NS['r']}}}id"] for sheet in workbook.findall(".//x:sheet", NS)
                      if sheet.attrib["name"] == "Golden Set")
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(rel.attrib["Target"] for rel in rels if rel.attrib["Id"] == rel_id)
        sheet = ET.fromstring(archive.read("xl/" + target.lstrip("/").removeprefix("xl/")))
        matrix = []
        for row in sheet.findall(".//x:sheetData/x:row", NS):
            values: dict[int, str] = {}
            for cell in row.findall("x:c", NS):
                idx = _column_index(cell.attrib["r"])
                value_node, inline = cell.find("x:v", NS), cell.find("x:is/x:t", NS)
                raw = (value_node.text if value_node is not None else inline.text if inline is not None else "") or ""
                values[idx] = strings[int(raw)] if cell.attrib.get("t") == "s" and raw else raw
            matrix.append([values.get(index, "") for index in range(max(values, default=-1) + 1)])
    headers = matrix[0]
    return [{headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))} for row in matrix[1:]]


def load_evaluation_rows(path) -> list[dict[str, str]]:
    """Load either the original XLSX benchmark or a leakage-isolated JSON holdout."""
    dataset_path = Path(path)
    if dataset_path.suffix.lower() != ".json":
        return load_golden_rows(dataset_path)
    rows = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Evaluation JSON must contain a list of cases.")
    required = {"Gold ID", "Include in Scoring", "Expected Issue", "Issue Subtype",
                "Old Manual Text", "Corrected Manual Text", "Expected Action"}
    ids = set()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or not required.issubset(row):
            missing = sorted(required - set(row) if isinstance(row, dict) else required)
            raise ValueError(f"Evaluation case {index} is missing fields: {', '.join(missing)}")
        if row["Gold ID"] in ids:
            raise ValueError(f"Duplicate evaluation Gold ID: {row['Gold ID']}")
        ids.add(row["Gold ID"])
    return rows


class EvaluationService:
    POSITIVE_TYPES = {"conflict", "unsupported_claim", "missing_requirement", "ambiguous"}

    def __init__(self, audit: AuditService | None = None):
        self.audit = audit or AuditService()

    @staticmethod
    def _failure_category(old_text: str, result, retrieval) -> str | None:
        if result.issue_type in EvaluationService.POSITIVE_TYPES:
            return None
        if not old_text.strip():
            return "parsing_failure"
        if not retrieval:
            return "retrieval_failure"
        if result.abstention_reason:
            return "unsupported_evidence" if "insufficient" in result.abstention_reason.lower() or "cannot establish" in result.abstention_reason.lower() or "not sufficiently related" in result.abstention_reason.lower() else "threshold_failure"
        return "reasoning_failure"

    @staticmethod
    def _correction_matches(suggestion: str | None, expected_action: str) -> bool:
        if not suggestion or not expected_action:
            return False
        expected_tokens = set(tokens(expected_action))
        predicted_tokens = set(tokens(suggestion))
        return len(expected_tokens & predicted_tokens) / max(1, len(expected_tokens)) >= 0.35

    @staticmethod
    def _retrieval_matches(expected: str, retrieved) -> bool:
        """Judge clause retrieval without penalising a correct passage embedded in a long chunk."""
        expected_tokens = set(tokens(expected))
        if not expected_tokens:
            return False
        for chunk, _ in retrieved:
            normalized = " ".join(chunk.text.split())
            passages = [normalized]
            passages.extend(part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", normalized)
                            if len(tokens(part)) >= 5)
            for passage in passages:
                passage_tokens = set(tokens(passage))
                containment = len(expected_tokens & passage_tokens) / min(
                    len(expected_tokens), max(1, len(passage_tokens)))
                if semantic_similarity(expected, passage) >= 0.25 or containment >= 0.55:
                    return True
        return False

    @classmethod
    def _first_relevant_rank(cls, expected: str, retrieved) -> int | None:
        for rank, item in enumerate(retrieved, start=1):
            if cls._retrieval_matches(expected, [item]):
                return rank
        return None

    def evaluate(self, rows: list[dict[str, str]] | None = None, mode: RAGMode = "deterministic") -> EvaluationResponse:
        scored = [row for row in (rows or load_golden_rows()) if row.get("Include in Scoring", "").strip().lower() == "yes"]
        cases = []
        for row in scored:
            # Strict leakage boundary: prediction sees only old text. All labels remain outside this call.
            old_text = row.get("Old Manual Text", "")
            started = time.perf_counter()
            result = (self.audit.audit(old_text, None) if mode == "deterministic"
                      else self.audit.audit(old_text, None, mode=mode))
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            retrieval_mode: RAGMode = "hybrid" if mode == "hybrid_llm" else mode
            retrieval = (self.audit.search.search(old_text, k=5,
                document_ids={"smcs-operations-manual-v2-corrected"}, mode=retrieval_mode)
                if getattr(self.audit, "search", None) else [])

            expected = row.get("Expected Issue", "").strip()
            expected_subtype = row.get("Issue Subtype", "").strip()
            expected_positive = expected != "no_issue"
            predicted_positive = result.issue_type in self.POSITIVE_TYPES
            outcome = ("true_positive" if expected_positive and predicted_positive else
                       "false_negative" if expected_positive else
                       "false_positive" if predicted_positive else "true_negative")
            expected_action = row.get("Expected Action", "").strip()
            # Evaluation-only relevance judgment happens after retrieval; corrected text never enters search.
            expected_evidence = row.get("Corrected Manual Text", "").strip()
            retrieval_rank = self._first_relevant_rank(expected_evidence, retrieval) if expected_evidence else None
            retrieval_hit = retrieval_rank is not None
            correction_correct = (self._correction_matches(result.suggested_correction, expected_action)
                                  if expected_positive else result.suggested_correction is None)
            top_chunk, top_score = retrieval[0] if retrieval else (None, None)
            cases.append(EvaluationCase(
                gold_id=row.get("Gold ID", ""), expected_issue=expected, expected_subtype=expected_subtype,
                predicted_issue=result.issue_type, predicted_subtype=result.issue_subtype,
                expected_positive=expected_positive, predicted_positive=predicted_positive,
                outcome=outcome, detected=predicted_positive,
                issue_type_correct=result.issue_type == expected,
                citation_correct=bool(result.citation and result.citation.document_id == "smcs-operations-manual-v2-corrected"),
                correction_correct=correction_correct, abstained=bool(result.abstention_reason),
                retrieval_result=(f"{top_chunk.document_title}; {top_chunk.section or 'section unavailable'}; page {top_chunk.page}: "
                                  f"{' '.join(top_chunk.text.split())[:500]}" if top_chunk else None),
                retrieval_score=round(top_score, 4) if top_score is not None else None,
                failure_category=self._failure_category(old_text, result, retrieval) if outcome == "false_negative" else None,
                latency_ms=latency_ms, retrieval_hit=retrieval_hit, retrieval_rank=retrieval_rank,
                reciprocal_rank=(1 / retrieval_rank if retrieval_rank else 0),
                ndcg_at_10=(1 / math.log2(retrieval_rank + 1) if retrieval_rank and retrieval_rank <= 10 else 0)))

        positives = [case for case in cases if case.expected_positive]
        negatives = [case for case in cases if not case.expected_positive]
        tp = sum(case.outcome == "true_positive" for case in cases)
        fn = sum(case.outcome == "false_negative" for case in cases)
        tn = sum(case.outcome == "true_negative" for case in cases)
        fp = sum(case.outcome == "false_positive" for case in cases)
        non_abstained = [case for case in cases if not case.abstained]
        correction_cases = positives
        return EvaluationResponse(
            scored_cases=len(cases), positive_cases=len(positives), negative_cases=len(negatives),
            true_positives=tp, false_negatives=fn, true_negatives=tn, false_positives=fp,
            detection_recall=tp / len(positives) if positives else None,
            false_positive_rate=fp / len(negatives) if negatives else None,
            issue_type_accuracy=sum(case.issue_type_correct for case in cases) / len(cases) if cases else 0,
            citation_accuracy=(sum(case.citation_correct for case in non_abstained) / len(non_abstained) if non_abstained else 0),
            correction_accuracy=(sum(case.correction_correct for case in correction_cases) / len(correction_cases) if correction_cases else 0),
            abstentions=sum(case.abstained for case in cases),
            metric_formulas={
                "detection_recall": "true_positives / positive_cases",
                "false_positive_rate": "false_positives / negative_cases",
                "issue_type_accuracy": "exact broad issue-type matches / total_scored_cases (abstentions count as incorrect)",
                "citation_accuracy": "non-abstained cases with a validated Corrected Operations Manual citation / non-abstained cases",
                "correction_accuracy": "positive cases whose suggested correction covers >= 35% of normalized Expected Action tokens / positive cases",
                "retrieval_recall_at_5": "evaluable cases whose top-5 contain a passage with >= 0.25 normalized semantic similarity or >= 0.55 token containment against evaluation-only Corrected Manual Text / cases with non-empty Corrected Manual Text; relevance is joined only after retrieval",
                "mean_reciprocal_rank": "mean of 1 / rank of the first relevant retrieved passage over evaluable cases",
                "ndcg_at_10": "mean discounted gain of the first relevant passage through rank 10 over evaluable cases",
            },
            limitation=(None if len(negatives) >= 5 else
                f"False-positive rate is based on only {len(negatives)} no-issue case(s) and cannot yet be measured reliably."),
            per_case=cases, mode=mode,
            retrieval_recall_at_k=(sum(case.retrieval_hit for case in cases) /
                                   sum(bool(row.get("Corrected Manual Text", "").strip()) for row in scored)
                                   if any(row.get("Corrected Manual Text", "").strip() for row in scored) else 0),
            retrieval_evaluable_cases=sum(bool(row.get("Corrected Manual Text", "").strip()) for row in scored),
            mean_reciprocal_rank=(sum(case.reciprocal_rank for case in cases) /
                                  sum(bool(row.get("Corrected Manual Text", "").strip()) for row in scored)
                                  if any(row.get("Corrected Manual Text", "").strip() for row in scored) else 0),
            ndcg_at_10=(sum(case.ndcg_at_10 for case in cases) /
                        sum(bool(row.get("Corrected Manual Text", "").strip()) for row in scored)
                        if any(row.get("Corrected Manual Text", "").strip() for row in scored) else 0),
            average_latency_ms=(sum(case.latency_ms for case in cases) / len(cases) if cases else 0))

    def compare(self, rows: list[dict[str, str]] | None = None) -> ComparisonResponse:
        benchmark_rows = rows or load_golden_rows()
        llm = GroundedLLMService()
        return ComparisonResponse(
            embedding_configuration=self.audit.search.embeddings.configuration,
            llm_configuration=llm.configuration,
            modes=[self.evaluate(benchmark_rows, mode=mode)
                   for mode in ("deterministic", "bm25", "dense", "rrf")],
        )
