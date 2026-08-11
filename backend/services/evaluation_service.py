import re
import zipfile
from xml.etree import ElementTree as ET

from backend.core.config import Config
from backend.models import EvaluationCase, EvaluationResponse
from backend.services.audit_service import AuditService
from backend.services.search_service import tokens


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

    def evaluate(self, rows: list[dict[str, str]] | None = None) -> EvaluationResponse:
        scored = [row for row in (rows or load_golden_rows()) if row.get("Include in Scoring", "").strip().lower() == "yes"]
        cases = []
        for row in scored:
            # Strict leakage boundary: prediction sees only old text. All labels remain outside this call.
            old_text = row.get("Old Manual Text", "")
            result = self.audit.audit(old_text, None)
            retrieval = (self.audit.search.search(old_text, k=1, document_ids={"smcs-operations-manual-v2-corrected"})
                         if getattr(self.audit, "search", None) else [])

            expected = row.get("Expected Issue", "").strip()
            expected_subtype = row.get("Issue Subtype", "").strip()
            expected_positive = expected != "no_issue"
            predicted_positive = result.issue_type in self.POSITIVE_TYPES
            outcome = ("true_positive" if expected_positive and predicted_positive else
                       "false_negative" if expected_positive else
                       "false_positive" if predicted_positive else "true_negative")
            expected_action = row.get("Expected Action", "").strip()
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
                failure_category=self._failure_category(old_text, result, retrieval) if outcome == "false_negative" else None))

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
            },
            limitation=(None if len(negatives) >= 5 else
                f"False-positive rate is based on only {len(negatives)} no-issue case(s) and cannot yet be measured reliably."),
            per_case=cases)
