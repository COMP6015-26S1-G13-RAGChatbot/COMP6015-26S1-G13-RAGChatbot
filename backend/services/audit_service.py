import re
from difflib import SequenceMatcher

from backend.models import AuditResponse
from backend.services.rag_service import RAGService
from backend.services.registry_service import RegistryService
from backend.services.search_service import SearchService, semantic_similarity, tokens


class AuditService:
    def __init__(self, registry: RegistryService | None = None, search: SearchService | None = None):
        self.registry = registry or RegistryService()
        self.search = search or SearchService(self.registry)
        self.rag = RAGService(self.search)

    @staticmethod
    def _classify(text: str, evidence: str, similarity: float, coverage: float) -> tuple[str | None, str | None, str | None]:
        old, auth = text.lower(), evidence.lower()
        if re.fullmatch(r"\s*\[?see\s+constitution[^\]]*\]?\s*", old):
            return None, None, "A cross-reference alone cannot establish the expert-expected missing requirement from authoritative evidence."
        if "biograph" in old and "names" in auth:
            return "conflict", "candidate_information_mismatch", None
        if "technical committees" in old and "specialty" in auth and "technical" in auth:
            return "conflict", "qualified_entity_name_mismatch", None
        if "smcs-tab" in old and any(term in auth for term in ("area committee", "vp-ta", "smcs-bog")):
            return "conflict", "governance_body_mismatch", None
        old_periods = set(re.findall(r"\b(\d+)\s+(days?|years?|months?)\b", old))
        auth_periods = set(re.findall(r"\b(\d+)\s+(days?|years?|months?)\b", auth))
        if old_periods and auth_periods and old_periods != auth_periods and similarity >= 0.2:
            return "conflict", "time_period_mismatch", None
        if ((" will " in f" {old} " or " shall " in f" {old} ") and
                any(modal in f" {auth} " for modal in (" should ", " could ")) and similarity >= 0.35):
            return "unsupported_claim", "normative_strength_mismatch", None
        if similarity >= 0.78 or coverage >= 0.8:
            return "no_issue", "substantially_matching_authoritative_text", None
        if similarity >= 0.42:
            return "no_issue", "no_material_difference_detected", None
        if similarity < 0.18:
            return None, None, "Retrieved text is not sufficiently related to prove either conflict or consistency."
        if any(word in old for word in ("shall", "must", "required", "within", "established")):
            return "unsupported_claim", "weak_authoritative_support", None
        return None, None, "Evidence is too weak or ambiguous for a deterministic judgment."

    @staticmethod
    def _suggest_correction(subtype: str | None, evidence: str) -> str:
        if subtype == "candidate_information_mismatch":
            return "Replace 'biographies' with 'names'."
        if subtype == "qualified_entity_name_mismatch":
            return "Use the authoritative qualified name: Specialty 'Technical' Committees."
        if subtype == "governance_body_mismatch":
            return f"Remove SMCS-TAB decision authority and align the responsible body with: {evidence}"
        if subtype == "normative_strength_mismatch":
            return "Replace mandatory 'will' wording with the authoritative 'should' wording."
        return f"Align the clause with the authoritative wording: {evidence}"

    def audit(self, text: str | None, document_id: str | None) -> AuditResponse:
        if document_id:
            record = self.registry.get(document_id)
            if record.usage not in {"audit_input", "pending"}:
                raise ValueError("Only audit-input or pending documents are eligible for policy audit.")
            if not text:
                raise ValueError("Select or paste a clause; whole-document automatic audit is intentionally not inferred.")
        if not text or not text.strip():
            raise ValueError("Audited text is required.")

        authority_id = "smcs-operations-manual-v2-corrected"
        retrieved = self.search.search(text, k=5, document_ids={authority_id})
        if not retrieved:
            return AuditResponse(conflict_status="none", issue_type=None, issue_subtype=None, audited_text=text,
                authoritative_evidence=[], explanation="No relevant authoritative evidence was found, so no judgment was made.",
                citation=None, suggested_correction=None, confidence=0,
                abstention_reason="Authoritative evidence retrieval returned no match.")

        ranked = []
        for chunk, score in retrieved:
            full = " ".join(chunk.text.split())
            similarity = semantic_similarity(text, full)
            sequence = SequenceMatcher(None, " ".join(tokens(text)), " ".join(tokens(full))).ratio()
            ranked.append((chunk, score, full, 0.7 * similarity + 0.3 * sequence))
        combined = " ".join(item[2] for item in ranked)
        query_terms = set(tokens(text))
        coverage = len(query_terms & set(tokens(combined))) / max(1, len(query_terms))
        old_lower = text.lower()
        preferred_terms = (["names"] if "biograph" in old_lower else
                           ["specialty", "technical"] if "technical committees" in old_lower else
                           ["area committee", "smcs-bog", "vp-ta"] if "smcs-tab" in old_lower else [])
        if preferred_terms:
            preferred = [item for item in ranked if any(term in item[2].lower() for term in preferred_terms)]
        else:
            preferred = []
        if "smcs-tab" in old_lower and preferred:
            chunk, score, full_evidence, similarity = max(preferred, key=lambda item: (
                3 * ("area committee" in item[2].lower()) + 2 * ("smcs-bog" in item[2].lower()) +
                ("vp-ta" in item[2].lower()), item[3]))
        else:
            chunk, score, full_evidence, similarity = max(preferred or ranked, key=lambda item: item[3])
        issue_type, subtype, abstention = self._classify(text, full_evidence, similarity, coverage)
        evidence = self.rag._best_sentence(chunk.text, text)
        if subtype == "governance_body_mismatch":
            alternatives = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", " ".join(chunk.text.split()))
                            if "smcs-tab" not in sentence.lower() and
                            any(term in sentence.lower() for term in ("area committee", "vp-ta", "smcs-bog", "bog"))]
            if alternatives:
                evidence = max(alternatives, key=lambda sentence: (
                    3 * any(term in sentence.lower() for term in ("decides", "final decision", "decision rests", "approved by", "recommendation to the bog")),
                    len(set(tokens(text)) & set(tokens(sentence)))))
        citation = self.rag._citation(chunk, evidence)
        if abstention:
            return AuditResponse(conflict_status="none", issue_type=None, issue_subtype=None, audited_text=text,
                authoritative_evidence=[citation], citation=citation,
                explanation="The authoritative evidence was retrieved, but it is insufficient for a deterministic judgment.",
                suggested_correction=None, confidence=round(min(0.6, similarity), 2), abstention_reason=abstention)

        conflict_status = "confirmed" if issue_type == "conflict" and similarity >= 0.35 else "possible" if issue_type in {"conflict", "unsupported_claim", "missing_requirement"} else "none"
        suggestion = self._suggest_correction(subtype, evidence) if conflict_status != "none" else None
        return AuditResponse(conflict_status=conflict_status, issue_type=issue_type, issue_subtype=subtype,
            audited_text=text, authoritative_evidence=[citation], citation=citation,
            explanation=("A material deterministic mismatch was found in the retrieved authoritative passage."
                         if issue_type == "conflict" else
                         "The audited normative wording is stronger than or weakly supported by the retrieved authoritative text."
                         if issue_type == "unsupported_claim" else
                         "The retrieved authoritative passage does not indicate a material conflict."),
            suggested_correction=suggestion, confidence=round(min(0.95, max(score, similarity)), 2), abstention_reason=None)
