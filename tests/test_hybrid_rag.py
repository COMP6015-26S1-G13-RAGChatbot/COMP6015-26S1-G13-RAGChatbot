import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from backend.services.audit_service import AuditService
from backend.services.embedding_service import EmbeddingService
from backend.services.evaluation_service import EvaluationService, load_evaluation_rows
from backend.services.ingest_service import SectionChunk
from backend.services.llm_service import GroundedLLMService
from backend.services.rag_service import RAGService
from backend.services.registry_service import RegistryService
from backend.services.search_service import SearchService, tokens


class FakeEmbeddings:
    configuration = {"backend": "test", "model": "fixed"}

    def __init__(self, scores):
        self.scores = scores

    def similarities(self, _query):
        return self.scores


class OllamaEmbeddingTests(unittest.TestCase):
    @patch("backend.services.embedding_service.httpx.post")
    def test_ollama_backend_embeds_documents_and_query(self, post):
        document_response = Mock()
        document_response.raise_for_status.return_value = None
        document_response.json.return_value = {"embeddings": [[1.0, 0.0], [0.0, 1.0]]}
        query_response = Mock()
        query_response.raise_for_status.return_value = None
        query_response.json.return_value = {"embeddings": [[1.0, 0.0]]}
        post.side_effect = [document_response, query_response]
        service = EmbeddingService(["unique alpha clause", "unique beta clause"], backend="ollama")
        scores = service.similarities("alpha")
        self.assertEqual(service.configuration,
                         {"backend": "ollama", "model": "nomic-embed-text:latest"})
        self.assertAlmostEqual(scores[0], 1.0)
        self.assertAlmostEqual(scores[1], 0.0)
        self.assertEqual(post.call_args_list[0].args[0], "http://127.0.0.1:11434/api/embed")


class EvaluationDatasetTests(unittest.TestCase):
    def test_blind_v2_dataset_has_unique_balanced_cases(self):
        rows = load_evaluation_rows(Path(__file__).with_name("blind_audit_set_v2.json"))
        self.assertEqual(len(rows), 50)
        self.assertEqual(len({row["Gold ID"] for row in rows}), 50)
        self.assertEqual(sum(row["Expected Issue"] == "no_issue" for row in rows), 25)
        self.assertTrue(all(row["Gold ID"].startswith("B") for row in rows))

    def test_retrieval_metric_accepts_correct_sentence_inside_long_chunk(self):
        expected = "Accounts must close within twelve months after the conference."
        chunk = SectionChunk(
            "long", "Background material. Accounts must close within twelve months after the conference. More guidance follows.",
            "smcs-operations-manual-v2-corrected", "Corrected Operations Manual", "2", "approved", 80,
            "production", "Financial reporting", "Financial reporting", 24)
        self.assertTrue(EvaluationService._retrieval_matches(expected, [(chunk, 0.5)]))

    def test_holdout_dataset_has_unique_balanced_cases(self):
        path = Path(__file__).with_name("holdout_audit_set.json")
        rows = load_evaluation_rows(path)
        self.assertEqual(len(rows), 50)
        self.assertEqual(len({row["Gold ID"] for row in rows}), 50)
        positives = [row for row in rows if row["Expected Issue"] != "no_issue"]
        self.assertEqual(len(positives), 25)

    def test_json_loader_rejects_duplicate_ids(self):
        row = {"Gold ID": "X", "Include in Scoring": "Yes", "Expected Issue": "no_issue",
               "Issue Subtype": "x", "Old Manual Text": "x", "Corrected Manual Text": "x",
               "Expected Action": "x"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps([row, row]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                load_evaluation_rows(path)


class HybridRAGTests(unittest.TestCase):
    def setUp(self):
        self.registry = RegistryService()
        self.production = SectionChunk(
            "prod", "The Society President appoints a qualified replacement when an officer position becomes formally vacant.",
            "smcs-operations-manual-v2-corrected", "Corrected Operations Manual", "2", "approved", 100,
            "production", "3.4 Officer vacancies", "Officer vacancies", 4,
        )
        self.evaluation = SectionChunk(
            "gold", "FORBIDDEN corrected answer and evaluator label.", "operations-golden-set",
            "Golden Set", "candidate", "evaluation_only", 0, "evaluation_only", None, None, 1,
        )

    def test_hybrid_vector_channel_can_retrieve_without_lexical_overlap(self):
        search = SearchService(self.registry, [self.production], FakeEmbeddings([0.95]))
        self.assertEqual(search.search("succession procedure", mode="deterministic"), [])
        self.assertEqual(search.search("succession procedure", mode="hybrid")[0][0].chunk_id, "prod")

    def test_bm25_dense_and_rrf_are_independent_research_modes(self):
        lexical = SectionChunk(
            "lexical", "Officer succession procedure and appointment process.",
            "smcs-operations-manual-v2-corrected", "Corrected Operations Manual", "2", "approved", 80,
            "production", "Succession", "Succession", 3)
        semantic = SectionChunk(
            "semantic", "A qualified replacement is selected for a formally vacant position.",
            "smcs-operations-manual-v2-corrected", "Corrected Operations Manual", "2", "approved", 80,
            "production", "Vacancy", "Vacancy", 4)
        search = SearchService(self.registry, [lexical, semantic], FakeEmbeddings([0.1, 0.95]))
        self.assertEqual(search.search("officer succession procedure", mode="bm25")[0][0].chunk_id, "lexical")
        self.assertEqual(search.search("officer succession procedure", mode="dense")[0][0].chunk_id, "semantic")
        rrf_ids = {chunk.chunk_id for chunk, _ in search.search("officer succession procedure", mode="rrf")}
        self.assertEqual(rrf_ids, {"lexical", "semantic"})

    def test_hybrid_filter_excludes_evaluation_content_before_ranking(self):
        search = SearchService(self.registry, [self.production, self.evaluation], FakeEmbeddings([0.7, 1.0]))
        results = search.search("corrected evaluator answer", mode="hybrid")
        self.assertNotIn("gold", {chunk.chunk_id for chunk, _ in results})

    def test_unsupported_hybrid_question_abstains(self):
        search = SearchService(self.registry, [self.production], FakeEmbeddings([0.0]))
        self.assertTrue(RAGService(search).answer("quantum banana reimbursement", "hybrid").abstained)

    def test_quantified_question_requires_subject_and_quantity_in_one_passage(self):
        reimbursement = SectionChunk(
            "reimbursement", "Travel reimbursement requests with actual necessary expenses should be submitted within sixty days.",
            "smcs-operations-manual-v2-corrected", "Corrected Operations Manual", "2", "approved", 80,
            "production", "Travel reimbursement", "Travel reimbursement", 10,
        )
        search = SearchService(self.registry, [reimbursement], FakeEmbeddings([0.95]))
        result = RAGService(search).answer(
            "What is the quantum banana reimbursement limit for an SMCS committee?", "hybrid")
        self.assertTrue(result.abstained)
        self.assertIn("quantified answer", result.answer)

    def test_related_shall_and_may_actions_are_not_automatically_a_conflict(self):
        leadership = SectionChunk(
            "leadership", "TC Chairs and Vice Chairs shall be appointed for four years. Leadership may be renewed once.",
            "smcs-operations-manual-v2-corrected", "Corrected Operations Manual", "2", "approved", 80,
            "production", "TC Leadership", "TC Leadership", 7,
        )
        procedure = SectionChunk(
            "procedure", "The area VP may consult a TC Chair. The TC Chair shall propose intended changes.",
            "smcs-operations-manual-v2-corrected", "Corrected Operations Manual", "2", "approved", 80,
            "production", "Change procedure", "Change procedure", 8,
        )
        search = SearchService(self.registry, [leadership, procedure], FakeEmbeddings([0.95, 0.7]))
        result = RAGService(search).answer(
            "How long is the term for a TC Chair or Vice-Chair, and may it be renewed?", "hybrid")
        self.assertFalse(result.abstained)
        self.assertEqual(result.conflict_status, "none")

    def test_no_key_falls_back_to_hybrid_without_changing_evidence(self):
        search = SearchService(self.registry, [self.production], FakeEmbeddings([0.9]))
        llm = GroundedLLMService(client=None)
        llm._client = None
        result = RAGService(search, llm).answer("Who appoints a replacement officer?", "hybrid_llm")
        self.assertEqual(result.mode, "hybrid")
        self.assertEqual(result.requested_mode, "hybrid_llm")
        self.assertIsNotNone(result.fallback_reason)
        self.assertTrue(result.citations)

    def test_deterministic_mode_is_reproducible(self):
        search = SearchService(self.registry, [self.production], FakeEmbeddings([0.9]))
        first = RAGService(search).answer("Who appoints a replacement officer?", "deterministic")
        second = RAGService(search).answer("Who appoints a replacement officer?", "deterministic")
        self.assertEqual((first.answer, first.citations, first.abstained),
                         (second.answer, second.citations, second.abstained))

    def test_regular_answer_returns_only_the_citation_it_uses(self):
        secondary = SectionChunk(
            "secondary", "The Society President consults the Board about replacement officers.",
            "smcs-constitution-bylaws-2023", "SMCS Constitution and Bylaws", "2023", "approved", 90,
            "production", "Officer consultation", "Officer consultation", 5,
        )
        search = SearchService(self.registry, [self.production, secondary], FakeEmbeddings([0.95, 0.9]))
        result = RAGService(search).answer("Who handles a replacement officer?", "hybrid")
        self.assertFalse(result.abstained)
        self.assertEqual(len(result.citations), 1)
        self.assertIn("[1]", result.answer)
        self.assertEqual(result.citations[0].document_id, self.production.document_id)

    def test_legacy_smcs_tab_query_expands_to_supported_area_committee(self):
        area_committee = SectionChunk(
            "area", "The corresponding Area Committee shall make the final decision about TC status.",
            "smcs-operations-manual-v2-corrected", "Corrected Operations Manual", "2", "approved", 80,
            "production", "TC governance", "TC governance", 4,
        )
        search = SearchService(self.registry, [area_committee], FakeEmbeddings([0.0]))
        result = search.search("SMCS-TAB governance status", mode="deterministic")
        self.assertEqual(result[0][0].chunk_id, "area")

    def test_lifecycle_terms_share_a_normalized_retrieval_token(self):
        self.assertIn("terminate", tokens("termination and discontinuation"))
        self.assertEqual(tokens("termination and discontinuation").count("terminate"), 2)


class AuditClassificationTests(unittest.TestCase):
    def test_structured_role_assignment_mismatch(self):
        issue, subtype = AuditService._structured_mismatch(
            "The VP for Publications shall chair the Conference Committee.",
            "The VP for Conferences shall chair the Conference Committee.")
        self.assertEqual((issue, subtype), ("conflict", "role_assignment_mismatch"))

    def test_structured_polarity_mismatch(self):
        issue, subtype = AuditService._structured_mismatch(
            "Insurance is never reimbursable for trip cancellation.",
            "Insurance for trip cancellation is reimbursable.")
        self.assertEqual((issue, subtype), ("unsupported_claim", "polarity_mismatch"))

    def test_unrelated_negation_in_long_evidence_does_not_create_polarity_mismatch(self):
        issue, _, _ = AuditService._classify(
            "The assistant maintains governance records and prepares reports.",
            "The assistant maintains governance records and prepares reports. The role does not approve budgets.",
            0.8, 1.0)
        self.assertEqual(issue, "no_issue")

    def test_structured_frequency_mismatch(self):
        issue, subtype = AuditService._structured_mismatch(
            "The committee must report monthly to the VP.",
            "The committee must report semi-annually to the VP.")
        self.assertEqual((issue, subtype), ("unsupported_claim", "reporting_frequency_mismatch"))

    def test_time_correction_names_old_and_authoritative_values(self):
        suggestion = AuditService._suggest_correction(
            "time_period_mismatch", "Reports are due within twelve months.",
            "Reports may be filed within twenty-four months.")
        self.assertIn("twenty-four months", suggestion)
        self.assertIn("twelve months", suggestion)

    def test_spelled_duration_mismatch_is_detected(self):
        issue, subtype, _ = AuditService._classify(
            "Reports may be filed after three years.",
            "Reports may be filed after one year.", 0.6, 0.8)
        self.assertEqual((issue, subtype), ("conflict", "time_period_mismatch"))

    def test_equivalent_calendar_durations_do_not_conflict(self):
        issue, subtype, _ = AuditService._classify(
            "The review occurs after twelve months.",
            "The review occurs after one year.", 0.7, 0.8)
        self.assertEqual(issue, "no_issue")

    def test_required_period_is_not_conflicted_by_extra_recommendation(self):
        issue, _, _ = AuditService._classify(
            "Accounts must close within twelve months.",
            "Accounts must close within twelve months; completion within six months is recommended.",
            0.7, 0.9)
        self.assertEqual(issue, "no_issue")

    def test_unsupported_numeric_requirement_is_detected(self):
        issue, subtype, _ = AuditService._classify(
            "A panel must hold eight meetings each year.",
            "A panel should hold two meetings each year.", 0.5, 0.7)
        self.assertEqual((issue, subtype), ("unsupported_claim", "quantified_requirement_mismatch"))

    def test_numeric_rule_is_compared_when_only_authority_uses_duration_unit(self):
        issue, subtype, _ = AuditService._classify(
            "A chapter must hold twelve meetings or be dissolved immediately.",
            "A chapter may be inactive after two meetings and dissolved after three years.", 0.4, 0.7)
        self.assertEqual((issue, subtype), ("unsupported_claim", "quantified_requirement_mismatch"))

    def test_missing_advance_approval_condition_is_detected(self):
        issue, subtype, _ = AuditService._classify(
            "Upgrades are reimbursed without prior approval.",
            "Upgrades must be approved in advance.", 0.45, 0.7)
        self.assertEqual((issue, subtype), ("conflict", "approval_condition_mismatch"))

    def test_without_phrase_cannot_remove_listed_eligibility_conditions(self):
        issue, subtype, _ = AuditService._classify(
            "A candidate qualifies even without registration or attendance.",
            "Eligibility: a candidate has registered and will attend the event.", 0.4, 0.7)
        self.assertEqual((issue, subtype), ("unsupported_claim", "missing_eligibility_conditions"))

    def test_probation_policy_is_unsupported_before_governance_actor_comparison(self):
        issue, subtype, abstention = AuditService._classify(
            "A TC shall enter a two-year probationary period with final review by SMCS-TAB.",
            "The Area Committee reviews TC activities.", 0.2, 0.5)
        self.assertEqual((issue, subtype, abstention),
                         ("unsupported_claim", "fabricated_probation_policy", None))

    def test_incidental_smcs_tab_assessment_does_not_create_a_conflict(self):
        issue, subtype, abstention = AuditService._classify(
            "TCs must submit reports which SMCS-TAB may use to assess long-term performance.",
            "TCs must submit reports about activities and future plans.", 0.5, 0.85)
        self.assertEqual((issue, subtype, abstention),
                         ("no_issue", "substantially_matching_authoritative_text", None))

    def test_correction_metric_accepts_equivalent_role_instruction(self):
        self.assertTrue(EvaluationService._correction_matches(
            "Replace the bare cross-reference by reproducing the authoritative role duties.",
            "Reproduce the President's duties from the controlling Constitution."))


if __name__ == "__main__":
    unittest.main()
