import unittest

from fastapi.testclient import TestClient

from backend.main import app
from backend.services.evaluation_service import EvaluationService, load_golden_rows
from backend.services.ingest_service import SectionChunk
from backend.services.rag_service import RAGService
from backend.services.registry_service import RegistryService
from backend.services.search_service import SearchService


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = RegistryService()

    def test_only_approved_production_documents_are_searchable(self):
        production = self.registry.production_documents()
        self.assertTrue(production)
        self.assertTrue(all(d.approval_status == "approved" and d.retrieval_enabled and d.usage == "production" for d in production))

    def test_old_pending_and_golden_set_are_excluded(self):
        ids = {d.document_id for d in self.registry.production_documents()}
        self.assertNotIn("smcs-operations-manual-v2-old", ids)
        self.assertNotIn("smcs-operations-manual-draft", ids)
        self.assertNotIn("operations-golden-set", ids)


class RetrievalAndRAGTests(unittest.TestCase):
    def setUp(self):
        self.registry = RegistryService()
        self.chunks = [
            SectionChunk("a", "Vacancies shall be filled within 30 days after announcement.",
                         "smcs-operations-manual-v2-corrected", "Corrected Operations Manual", "2", "approved", 100, "production", "3.4 Vice-President", "Vacancies", 4),
            SectionChunk("b", "Vacancies shall be filled within 60 days after announcement.",
                         "smcs-technical-manual-2023", "SMCS Technical Manual", "2023", "approved", 70, "production", "4", "Vacancies", 2),
            SectionChunk("old", "Secret old manual answer within 90 days.",
                         "smcs-operations-manual-v2-old", "Old Operations Manual V5", "old", "superseded", 10, "audit_input", "1", None, 1),
        ]
        self.search = SearchService(self.registry, self.chunks)

    def test_search_excludes_non_production_chunk(self):
        results = self.search.search("old manual secret answer")
        self.assertEqual(results, [])

    def test_highest_authority_controls_conflicting_answer(self):
        result = RAGService(self.search).answer("Within how many days shall vacancies be filled after announcement?")
        self.assertFalse(result.abstained)
        self.assertEqual(result.conflict_status, "possible")
        self.assertIn("Applying the configured authority rule", result.answer)
        self.assertEqual(result.citations[0].document_id, "smcs-operations-manual-v2-corrected")

    def test_missing_evidence_abstains(self):
        result = RAGService(self.search).answer("quantum banana reimbursement")
        self.assertTrue(result.abstained)
        self.assertEqual(result.citations, [])

    def test_citation_validation_rejects_fabricated_evidence(self):
        from backend.models import Citation
        fake = Citation(document_id="smcs-operations-manual-v2-corrected", document_title="Corrected Operations Manual", section="3.4", page=4, evidence_text="fabricated")
        self.assertEqual(RAGService.validate_citations([fake], [(self.chunks[0], 1.0)]), [])

    def test_chat_does_not_concatenate_unrelated_retrievals(self):
        unrelated = SectionChunk("c", "The newsletter editor publishes awards announcements.",
            "smcs-operations-manual-v2-corrected", "Corrected Operations Manual", "2", "approved", 100,
            "production", "9 Publications", "Publications", 12)
        result = RAGService(SearchService(self.registry, self.chunks + [unrelated])).answer(
            "Within how many days shall vacancies be filled after announcement?")
        self.assertNotIn("newsletter", result.answer.lower())

    def test_real_section_label_is_preserved(self):
        result = RAGService(self.search).answer("Within how many days shall vacancies be filled after announcement?")
        self.assertEqual(result.citations[0].section, "3.4 Vice-President")


class EvaluationIsolationTests(unittest.TestCase):
    def test_workbook_loader_finds_only_scored_flag_later(self):
        rows = load_golden_rows()
        self.assertEqual(len(rows), 14)
        self.assertEqual(sum(r["Include in Scoring"].lower() == "yes" for r in rows), 12)

    def test_prediction_receives_only_old_text(self):
        class SpyAudit:
            def audit(self, text, document_id):
                self.seen = text
                from backend.models import AuditResponse
                return AuditResponse(conflict_status="none", issue_type="no_issue", audited_text=text,
                    authoritative_evidence=[], explanation="test", citation=None,
                    suggested_correction=None, confidence=0.5, abstention_reason=None)
        spy = SpyAudit()
        rows = [{"Gold ID": "X", "Old Manual Text": "INPUT_ONLY", "Corrected Manual Text": "FORBIDDEN_CORRECTED",
                 "Tom's Comment": "FORBIDDEN_COMMENT", "Expected Issue": "no_issue", "Include in Scoring": "Yes"}]
        result = EvaluationService(spy).evaluate(rows)
        self.assertEqual(spy.seen, "INPUT_ONLY")
        self.assertEqual(result.scored_cases, 1)

    def test_metric_denominators_and_confusion_matrix_are_explicit(self):
        result = EvaluationService().evaluate()
        self.assertEqual(result.scored_cases, result.positive_cases + result.negative_cases)
        self.assertEqual(result.positive_cases, result.true_positives + result.false_negatives)
        self.assertEqual(result.negative_cases, result.true_negatives + result.false_positives)
        self.assertAlmostEqual(result.detection_recall, result.true_positives / result.positive_cases)
        self.assertAlmostEqual(result.false_positive_rate, result.false_positives / result.negative_cases)

    def test_supported_negative_clauses_are_not_flagged(self):
        from backend.services.audit_service import AuditService
        clauses = [
            "TC members are expected to attend at least 50% of TC meetings annually and contribute to at least one TC activity each year.",
            "Within-term vacancies of a Vice President shall be filled by the President within 30 days of the vacancy’s formal announcement to the BoG, from two candidates with names provided by the Nominations Committee.",
            "Each TC shall undergo a comprehensive review every four years by the appropriate VP-TA.",
        ]
        for clause in clauses:
            with self.subTest(clause=clause):
                self.assertEqual(AuditService().audit(clause, None).conflict_status, "none")


class ApiTests(unittest.TestCase):
    def test_structured_chat_output_and_validation(self):
        with TestClient(app) as client:
            response = client.post("/api/chat", json={"question": "What is the role of the President?"})
            self.assertEqual(response.status_code, 200)
            self.assertTrue({"answer", "citations", "conflict_status", "confidence", "abstained"} <= response.json().keys())
            self.assertEqual(client.post("/api/chat", json={"question": ""}).status_code, 422)

    def test_api_never_exposes_internal_source_paths(self):
        with TestClient(app) as client:
            payload = client.post("/api/chat", json={"question": "What is the Society membership requirement?"}).json()
            self.assertNotIn("/Users/", str(payload))

    def test_development_retrieval_debug_is_bounded_and_explanatory(self):
        with TestClient(app) as client:
            payload = client.post("/api/debug/retrieval", json={"query": "Vice President vacancy within 30 days"}).json()
            self.assertEqual(payload["query"], "Vice President vacancy within 30 days")
            self.assertTrue(payload["candidates"])
            self.assertTrue(all("reason" in item and "authority_level" in item for item in payload["candidates"]))


if __name__ == "__main__":
    unittest.main()
