import unittest

from backend.services.ingest_service import SectionChunk
from backend.services.audit_service import AuditService
from backend.services.llm_service import GroundedLLMService
from backend.services.rag_service import RAGService
from backend.services.registry_service import RegistryService
from backend.services.search_service import SearchService


def chunk(chunk_id, text, document_id, title, authority, section, page=1, version="approved-v1"):
    return SectionChunk(chunk_id, text, document_id, title, version, "approved", authority,
                        "production", section, section, page)


class ConfirmedAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.registry = RegistryService()

    def answer(self, chunks, question="Who shall or may fill the governance vacancy within the stated period?"):
        return RAGService(SearchService(self.registry, chunks)).answer(question)

    def assert_hierarchy_resolution(self, result, higher_id, higher_score, lower_score):
        self.assertEqual(result.conflict_status, "confirmed")
        self.assertEqual(result.conflict_scope, "cross_document")
        self.assertEqual(result.higher_authority_evidence.document_id, higher_id)
        self.assertEqual(result.higher_authority_evidence.authority_score, higher_score)
        self.assertEqual({citation.authority_score for citation in result.conflicting_evidence},
                         {higher_score, lower_score})
        self.assertEqual(len(result.citations), 2)
        self.assertIn("Resolved by document hierarchy", result.resolution_basis)
        self.assertFalse(result.human_review_required)
        self.assertTrue(all(citation.approval_status == "approved" and citation.version for citation in result.citations))

    def test_ieee_overrides_smcs_or_manual(self):
        ieee = chunk("ieee", "The Assembly shall fill the governance vacancy within 30 days.",
            "ieee-constitution-bylaws-2024", "IEEE Constitution and Bylaws", 100, "Bylaw I-301.12", 10)
        smcs = chunk("smcs", "The committee may fill the governance vacancy within 60 days.",
            "smcs-constitution-bylaws-2023", "SMCS Constitution and Bylaws", 90, "Article VI", 4)
        self.assert_hierarchy_resolution(self.answer([ieee, smcs]), ieee.document_id, 100, 90)

    def test_smcs_constitution_overrides_operations_manual(self):
        smcs = chunk("smcs", "The Board shall fill the governance vacancy within 30 days.",
            "smcs-constitution-bylaws-2023", "SMCS Constitution and Bylaws", 90, "Article VI", 4)
        manual = chunk("manual", "The Board may fill the governance vacancy within 60 days.",
            "smcs-operations-manual-v2-corrected", "Corrected Operations Manual", 80, "3.4", 8)
        self.assert_hierarchy_resolution(self.answer([smcs, manual]), smcs.document_id, 90, 80)

    def test_operations_manual_overrides_technical_manual(self):
        manual = chunk("manual", "The Board shall fill the governance vacancy within 30 days.",
            "smcs-operations-manual-v2-corrected", "Corrected Operations Manual", 80, "3.4", 8)
        technical = chunk("technical", "The Board may fill the governance vacancy within 60 days.",
            "smcs-technical-manual-2023", "SMCS Technical Manual", 70, "4.2", 9)
        self.assert_hierarchy_resolution(self.answer([manual, technical]), manual.document_id, 80, 70)

    def test_registry_uses_supervisor_confirmed_hierarchy(self):
        scores = {record.document_id: record.authority_level for record in self.registry.production_documents()}
        self.assertEqual(scores, {
            "smcs-operations-manual-v2-corrected": 80,
            "smcs-technical-manual-2023": 70,
            "smcs-constitution-bylaws-2023": 90,
            "ieee-constitution-bylaws-2024": 100,
        })

    def test_equal_authority_cross_document_conflict_requires_human_review(self):
        left = chunk("left", "The Board shall fill the governance vacancy within 30 days.",
            "smcs-operations-manual-v2-corrected", "Policy A", 80, "Vacancies", 2)
        right = chunk("right", "The Board may fill the governance vacancy within 60 days.",
            "smcs-technical-manual-2023", "Policy B", 80, "Vacancies", 5)
        result = self.answer([left, right])
        self.assertEqual(result.conflict_scope, "cross_document")
        self.assertEqual(result.conflict_status, "possible")
        self.assertTrue(result.human_review_required)
        self.assertTrue(result.abstained)
        self.assertIsNone(result.higher_authority_evidence)
        self.assertEqual(len(result.conflicting_evidence), 2)
        self.assertIn("equal authority", result.resolution_basis.lower())


class InternalConflictTests(unittest.TestCase):
    def setUp(self):
        registry = RegistryService()
        document_id, title = "ieee-constitution-bylaws-2024", "IEEE Constitution and Bylaws"
        self.chunks = [
            chunk("special", "If a Region or Division fails to fill a vacancy in the office of Region/Division Delegate within six months following notice of such vacancy, a special meeting of the Assembly shall be called within 90 calendar days thereafter to fill such vacancy.", document_id, title, 100, "Bylaw I-202.2 — Special Meetings", 12),
            chunk("may", "If such Region or Division shall fail to elect a Director within six months after notice of such vacancy, the vacancy may be filled by the Assembly even if the number of Directors elected by the voting members shall be less than 60% of the total number of Directors, provided that a Director elected by the Assembly shall not be a Delegate.", document_id, title, 100, "Bylaw I-301.12(7) — Vacancies", 23),
            chunk("shall", "In the event that an organizational unit fails to elect a Director-Elect or fill the Director vacancy within six months, the vacancy shall be filled by the Assembly.", document_id, title, 100, "Bylaw I-301.12(8) — Vacancies", 24),
        ]
        self.search = SearchService(registry, self.chunks)
        self.question = "If a Region or organizational unit fails within six months, shall or may the Assembly fill the Delegate, Director, or Director-Elect vacancy?"

    def test_shall_versus_may_is_not_falsely_resolved_by_hierarchy(self):
        result = RAGService(self.search).answer(self.question)
        self.assertEqual(result.conflict_status, "ambiguous_internal_conflict")
        self.assertEqual(result.conflict_scope, "within_document")
        self.assertIsNone(result.higher_authority_evidence)
        self.assertTrue(result.human_review_required)
        self.assertTrue(result.abstained)
        self.assertEqual({"shall", "may"} <= set(result.conflicting_normative_terms), True)
        self.assertGreaterEqual(len(result.citations), 2)
        self.assertTrue(all(citation.document_id == "ieee-constitution-bylaws-2024" for citation in result.citations))
        self.assertIn("cannot resolve", result.answer)
        self.assertTrue(any("requiring" in item for item in result.interpretations))
        self.assertTrue(any("permitting" in item for item in result.interpretations))

    def test_llm_unavailable_preserves_deterministic_internal_conflict(self):
        llm = GroundedLLMService(client=None)
        llm._client = None
        result = RAGService(self.search, llm).answer(self.question, "hybrid_llm")
        self.assertEqual(result.conflict_status, "ambiguous_internal_conflict")
        self.assertTrue(result.human_review_required)
        self.assertGreaterEqual(len(result.citations), 2)
        self.assertNotEqual(result.mode, "hybrid_llm")

    def test_policy_audit_exposes_the_same_unresolved_internal_conflict(self):
        result = AuditService(RegistryService(), self.search).audit(self.question, None)
        self.assertEqual(result.conflict_scope, "within_document")
        self.assertEqual(result.conflict_status, "ambiguous_internal_conflict")
        self.assertIsNone(result.higher_authority_evidence)
        self.assertTrue(result.human_review_required)
        self.assertGreaterEqual(len(result.authoritative_evidence), 2)


if __name__ == "__main__":
    unittest.main()
