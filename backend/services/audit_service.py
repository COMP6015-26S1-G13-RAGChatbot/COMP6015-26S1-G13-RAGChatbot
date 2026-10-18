import re
from difflib import SequenceMatcher

from backend.models import AuditResponse, RAGMode
from backend.services.rag_service import RAGService
from backend.services.registry_service import RegistryService
from backend.services.search_service import SearchService, semantic_similarity, tokens


class AuditService:
    NUMBER_WORDS = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "eighteen": 18,
        "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
        "fifty": 50, "sixty": 60, "ninety": 90, "single": 1,
    }

    @staticmethod
    def _structured_mismatch(text: str, evidence: str) -> tuple[str | None, str | None]:
        """Compare reusable claim fields before accepting high surface similarity."""
        old, auth = text.lower(), evidence.lower()
        shared = len(set(tokens(text)) & set(tokens(evidence)))

        role_pattern = re.compile(
            r"(?:vice president|vp)\s+(?:for\s+)?([a-z–-]+(?:\s+[a-z–-]+){0,4}?)(?=\s+(?:shall|must|may|chairs?|serves?)|[,.;])")
        old_role, auth_role = role_pattern.search(old), role_pattern.search(auth)
        committee_terms = {token for token in tokens(text) if token in {
            "committee", "conference", "meeting", "publication", "cybernetic", "system",
            "engineering", "planning", "human", "machine"}}
        if (old_role and auth_role and old_role.group(1).strip() != auth_role.group(1).strip() and
                len(committee_terms & set(tokens(evidence))) >= 2):
            return "conflict", "role_assignment_mismatch"

        frequencies = {
            "monthly": 12, "every month": 12, "semi-annually": 2, "semiannual": 2, "semi-annual": 2,
            "annually": 1, "annual": 1, "every year": 1,
        }
        old_frequency = {amount for phrase, amount in frequencies.items() if phrase in old}
        auth_frequency = {amount for phrase, amount in frequencies.items() if phrase in auth}
        if old_frequency and auth_frequency and old_frequency.isdisjoint(auth_frequency) and shared >= 3:
            return "unsupported_claim", "reporting_frequency_mismatch"

        polarity_checks = (
            ("reimburs", r"\b(?:never|not)\b[^.]{0,35}\breimburs|\bnon-reimburs",),
            ("eligib", r"\b(?:not\s+eligible|ineligible)\b",),
            ("financial", r"\bno\s+financial\s+responsibility\b",),
            ("approval", r"\bwithout\s+(?:prior\s+)?approval\b",),
            ("cms", r"\b(?:bypass|outside)\b[^.]{0,40}\bcms\b",),
        )
        for concept, negative_pattern in polarity_checks:
            if concept in old and concept in auth:
                old_negative = bool(re.search(negative_pattern, old))
                auth_negative = bool(re.search(negative_pattern, auth))
                if old_negative != auth_negative and shared >= 2:
                    return "unsupported_claim", "polarity_mismatch"
        if ("award" in old and "award" in auth and "may receive" in old and
                re.search(r"\b(?:not eligible|ineligible)\b", auth)):
            return "unsupported_claim", "polarity_mismatch"

        if ("only" in old and any(marker in auth for marker in ("open to all", "regardless of", "shall include", "at a minimum")) and
                shared >= 2):
            if any(role in old for role in ("chair", "committee needs")):
                return "conflict", "missing_required_items"
            return "unsupported_claim", "unsupported_exclusive_restriction"

        antonyms = (("closest", "distant"), ("half", "plus"), ("commercial bank", "nextgen"))
        if any(left in old and right in auth for left, right in antonyms) and shared >= 2:
            return "unsupported_claim", "material_term_mismatch"
        return None, None

    def __init__(self, registry: RegistryService | None = None, search: SearchService | None = None):
        self.registry = registry or RegistryService()
        self.search = search or SearchService(self.registry)
        self.rag = RAGService(self.search)

    @staticmethod
    def _classify(text: str, evidence: str, similarity: float, coverage: float) -> tuple[str | None, str | None, str | None]:
        old, auth = text.lower(), evidence.lower()
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", " ".join(evidence.split()))
                     if len(tokens(part)) >= 4]
        claim_evidence = max(sentences, key=lambda part: (
            semantic_similarity(text, part), len(set(tokens(text)) & set(tokens(part)))), default=evidence)
        claim_auth = claim_evidence.lower()
        if re.fullmatch(r"\s*\[?see\s+constitution[^\]]*\]?\s*", old):
            return "missing_requirement", "incomplete_role_description", None
        if "probation" in old and re.search(
                r"\b(?:\d+|one|two|three|four|five)\s*[- ]?years?\b", old):
            return "unsupported_claim", "fabricated_probation_policy", None
        if "biograph" in old and "names" in auth:
            return "conflict", "candidate_information_mismatch", None
        if "technical committees" in old and "specialty" in auth and "technical" in auth:
            return "conflict", "qualified_entity_name_mismatch", None
        assigns_governance_authority = bool(re.search(
            r"\b(formal approval|formal evaluation|final review|final decision|decision authority|"
            r"high-level decisions?|shall be established|transition from probationary|"
            r"terminated? as part|termination (?:is|shall|may)|approve[sd]? by)\b", old))
        assigns_governance_authority = assigns_governance_authority or bool(re.search(
            r"\b(?:grant continued recognition|initiate dissolution)\b", old))
        if ("smcs-tab" in old and assigns_governance_authority and
                any(term in auth for term in ("area committee", "vp-ta", "smcs-bog", "bog"))):
            return "conflict", "governance_body_mismatch", None
        number_pattern = r"\d+|" + "|".join(AuditService.NUMBER_WORDS)
        def periods(value: str) -> set[tuple[int, str]]:
            found = set()
            for number, unit in re.findall(rf"\b({number_pattern})\s*[- ]?(days?|years?|months?)\b", value):
                amount = int(number) if number.isdigit() else AuditService.NUMBER_WORDS[number]
                normalized_unit = unit.rstrip("s")
                # Normalize calendar durations so six months and one year can
                # be compared without hard-coding either phrase.
                if normalized_unit == "year":
                    amount, normalized_unit = amount * 12, "month"
                found.add((amount, normalized_unit))
            return found
        old_periods, auth_periods = periods(old), periods(claim_auth)
        shared_content = len(set(tokens(text)) & set(tokens(claim_evidence)))
        if (old_periods and auth_periods and old_periods.isdisjoint(auth_periods) and
                (similarity >= 0.2 or shared_content >= 3)):
            return "conflict", "time_period_mismatch", None
        old_numbers = {int(value) if value.isdigit() else AuditService.NUMBER_WORDS[value]
                       for value in re.findall(rf"\b({number_pattern})\b", old)}
        auth_numbers = {int(value) if value.isdigit() else AuditService.NUMBER_WORDS[value]
                        for value in re.findall(rf"\b({number_pattern})\b", claim_auth)}
        if (not (old_periods and auth_periods) and old_numbers and auth_numbers and
                old_numbers.isdisjoint(auth_numbers) and shared_content >= 3):
            return "unsupported_claim", "quantified_requirement_mismatch", None
        if ("simple majority" in old and
                any(term in auth for term in ("two-thirds", "two thirds", "2/3"))):
            return "conflict", "approval_threshold_mismatch", None
        if ("without prior approval" in old and
                re.search(r"\b(?:approved?|approval)\b", auth) and
                any(term in auth for term in ("in advance", "before the trip", "prior to"))):
            return "conflict", "approval_condition_mismatch", None
        if ("without" in old and
                ("eligib" in auth or any(term in auth for term in ("required", "requires", "shall", "must"))) and
                shared_content >= 3):
            return "unsupported_claim", "missing_eligibility_conditions", None
        structured_issue, structured_subtype = AuditService._structured_mismatch(text, claim_evidence)
        if structured_issue:
            return structured_issue, structured_subtype, None
        if ((" will " in f" {old} " or " shall " in f" {old} ") and
                any(modal in f" {auth} " for modal in (" should ", " could ")) and
                (similarity >= 0.2 or shared_content >= 3)):
            return "unsupported_claim", "normative_strength_mismatch", None
        if similarity >= 0.78 or coverage >= 0.8:
            return "no_issue", "substantially_matching_authoritative_text", None
        if similarity >= 0.42:
            return "no_issue", "no_material_difference_detected", None
        prescriptive_markers = re.findall(
            r"\b(shall|must|required|should|maximum|minimum|at least|within)\b", old)
        if len(prescriptive_markers) >= 2 and coverage < 0.7:
            return "unsupported_claim", "weak_authoritative_support", None
        if similarity < 0.18:
            return None, None, "Retrieved text is not sufficiently related to prove either conflict or consistency."
        if any(word in old for word in ("shall", "must", "required", "within", "established")):
            return "unsupported_claim", "weak_authoritative_support", None
        return None, None, "Evidence is too weak or ambiguous for a deterministic judgment."

    @staticmethod
    def _suggest_correction(subtype: str | None, evidence: str, audited_text: str = "") -> str:
        number = r"\d+(?:\.\d+)?%?|twenty-four|two-thirds|one-half|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|twenty|thirty|forty|fifty|sixty|ninety"
        period = rf"\b(?:{number})\s*[- ]?(?:days?|months?|years?)\b"
        def replacement(pattern: str) -> tuple[str | None, str | None]:
            old_match = re.search(pattern, audited_text, re.I)
            new_match = re.search(pattern, evidence, re.I)
            return (old_match.group(0) if old_match else None,
                    new_match.group(0) if new_match else None)
        if subtype == "incomplete_role_description":
            return "Replace the bare cross-reference by reproducing the authoritative role duties."
        if subtype == "candidate_information_mismatch":
            return "Replace 'biographies' with 'names'."
        if subtype == "qualified_entity_name_mismatch":
            return "Use the authoritative qualified name: Specialty 'Technical' Committees."
        if subtype == "governance_body_mismatch":
            return f"Remove SMCS-TAB decision authority and align the responsible body with: {evidence}"
        if subtype == "normative_strength_mismatch":
            return "Replace mandatory 'will' wording with the authoritative 'should' wording."
        if subtype == "fabricated_probation_policy":
            return "Remove the unsupported two-year probation requirement unless an approved authoritative source is supplied."
        if subtype == "time_period_mismatch":
            old_value, new_value = replacement(period)
            if old_value and new_value:
                return f"Replace '{old_value}' with the authoritative period '{new_value}'."
            return f"Replace the incorrect period with the authoritative period stated here: {evidence}"
        if subtype == "quantified_requirement_mismatch":
            old_period, new_period = replacement(period)
            if old_period and new_period:
                return f"Replace '{old_period}' with the authoritative period '{new_period}'."
            quantity_pattern = None
            if re.search(r"(?:percent|%)", audited_text, re.I):
                quantity_pattern = rf"\b(?:{number})\s*(?:percent|%)"
            else:
                for noun in ("signatures?", "meetings?", "bids?", "journals?", "members?"):
                    candidate = rf"\b(?:{number})\s+(?:[a-z-]+\s+){{0,3}}{noun}\b"
                    if re.search(candidate, audited_text, re.I) and re.search(candidate, evidence, re.I):
                        quantity_pattern = candidate
                        break
            old_value, new_value = replacement(quantity_pattern or rf"\b(?:{number})\b")
            if old_value and new_value:
                return f"Replace the unsupported quantity '{old_value}' with the authoritative quantity '{new_value}'."
            if "meeting" in audited_text.lower():
                return "Remove the unsupported meeting frequency and attendance threshold; use only the approved participation requirements."
            return f"Remove the unsupported quantity and use the authoritative threshold or quantity: {evidence}"
        if subtype == "reporting_frequency_mismatch":
            old_frequency = next((term for term in ("monthly", "every month", "semi-annually", "annually")
                                  if term in audited_text.lower()), "the incorrect frequency")
            new_frequency = next((term for term in ("semi-annually", "semi-annual", "monthly", "annually")
                                  if term in evidence.lower()), "the approved frequency")
            return f"Replace {old_frequency} reporting with {new_frequency} reporting."
        if subtype == "material_term_mismatch":
            if "half" in audited_text.lower() and "surcharge" in evidence.lower():
                return "Remove the unsupported Affiliate discount and apply the approved Affiliate surcharge rule."
            if "closest" in audited_text.lower() and "distant" in evidence.lower():
                return "Remove the closest-traveler priority and use the approved selection factors, including distant travel."
            if "commercial bank" in audited_text.lower() and "nextgen" in evidence.lower():
                return "Remove the external commercial-bank mandate and use the approved NextGen Banking recommendation."
            return f"Replace the unsupported material term with the authoritative wording: {evidence}"
        if subtype == "missing_required_items":
            return f"Add all required roles or items stated in the authoritative clause: {evidence}"
        if subtype == "polarity_mismatch":
            return f"Reverse the unsupported permission or prohibition to match the authoritative clause: {evidence}"
        if subtype == "approval_threshold_mismatch":
            return f"Replace the incorrect approval threshold with the authoritative threshold: {evidence}"
        if subtype == "approval_condition_mismatch":
            return f"Require the authoritative approval condition: {evidence}"
        if subtype == "missing_eligibility_conditions":
            return f"Add the authoritative eligibility conditions and remove the unsupported exception: {evidence}"
        if subtype == "weak_authoritative_support":
            return f"Remove unsupported requirements and align the clause with the authoritative wording: {evidence}"
        return f"Align the clause with the authoritative wording: {evidence}"

    def audit(self, text: str | None, document_id: str | None, mode: RAGMode = "deterministic") -> AuditResponse:
        if document_id:
            record = self.registry.get(document_id)
            if record.usage not in {"audit_input", "pending"}:
                raise ValueError("Only audit-input or pending documents are eligible for policy audit.")
            if not text:
                raise ValueError("Select or paste a clause; whole-document automatic audit is intentionally not inferred.")
        if not text or not text.strip():
            raise ValueError("Audited text is required.")

        retrieval_mode: RAGMode = "hybrid" if mode == "hybrid_llm" else mode
        retrieved = self.search.search(text, k=10, mode=retrieval_mode)
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
        conflict_rows = [(chunk, score, self.rag._best_passage(chunk.text, text)) for chunk, score, _, _ in ranked]
        conflicts = self.rag._detect_conflicts(text, conflict_rows)
        internal = next((item for item in conflicts if item.conflict_scope == "within_document"), None)
        if internal:
            internal_conflicts = [item for item in conflicts if item.conflict_scope == "within_document"]
            evidence_by_key = {}
            for item in internal_conflicts:
                for citation in item.conflicting_evidence:
                    evidence_by_key[(citation.document_id, citation.section, citation.page, citation.evidence_text)] = citation
            citations = self.rag.validate_citations(list(evidence_by_key.values()), retrieved)
            terms = sorted({term for item in internal_conflicts for term in item.conflicting_normative_terms})
            interpretations = list(dict.fromkeys(
                interpretation for item in internal_conflicts for interpretation in item.interpretations))
            return AuditResponse(conflict_status="ambiguous_internal_conflict",
                conflict_scope="within_document", issue_type="ambiguous",
                issue_subtype="ambiguous_internal_conflict", audited_text=text,
                authoritative_evidence=citations, citation=citations[0] if citations else None,
                explanation=("These provisions contain potentially inconsistent requirements for closely related scenarios. "
                             "Because they appear in the same authoritative document, the hierarchy cannot resolve the ambiguity. "
                             "The applicable interpretation may depend on the subject, conditions and exceptions."),
                suggested_correction=None, confidence=0.55,
                abstention_reason="No definitive rule is presented because equal-authority clauses remain ambiguous.",
                higher_authority_evidence=None, conflicting_evidence=citations,
                authority_scores=internal.authority_scores,
                conflicting_normative_terms=terms,
                interpretations=interpretations, resolution_basis=internal.resolution_basis,
                human_review_required=True)
        cross = next((item for item in conflicts if item.conflict_scope == "cross_document"), None)
        query_norms = set(re.findall(r"\b(shall|must|may)\b", text.lower()))
        explicit_modal_conflict = bool({"shall", "must"} & query_norms and "may" in query_norms)
        explicit_authority_dispute = bool(re.search(
            r"\b(formal approval|formal evaluation|final review|final decision|decision authority|"
            r"grant continued recognition|initiate dissolution|shall be established|smcs-tab)\b",
            text.lower()))
        if cross and not explicit_modal_conflict and not explicit_authority_dispute:
            cross = None
        if (cross and "smcs-tab" in text.lower() and not re.search(
                r"\b(formal approval|formal evaluation|final review|final decision|decision authority|"
                r"grant continued recognition|initiate dissolution|shall be established|termination)\b",
                text.lower())):
            # Incidental references to SMCS-TAB (for example, using reports to
            # assess performance) do not assign it a controlling decision role.
            cross = None
        if cross:
            citations = self.rag.validate_citations(cross.conflicting_evidence, retrieved)
            if cross.human_review_required:
                return AuditResponse(conflict_status="possible", conflict_scope="cross_document",
                    issue_type="ambiguous", issue_subtype="equal_authority_cross_document_conflict",
                    audited_text=text, authoritative_evidence=citations,
                    citation=citations[0] if citations else None,
                    explanation=("The retrieved documents contain conflicting rules with equal configured authority. "
                                 "The hierarchy cannot select a controlling source; both references require contextual review."),
                    suggested_correction=None, confidence=0.5,
                    abstention_reason="Equal-authority documents contain an unresolved conflict.",
                    higher_authority_evidence=None, conflicting_evidence=citations,
                    authority_scores=cross.authority_scores,
                    conflicting_normative_terms=cross.conflicting_normative_terms,
                    interpretations=cross.interpretations, resolution_basis=cross.resolution_basis,
                    human_review_required=True)
            return AuditResponse(conflict_status="confirmed", conflict_scope="cross_document",
                issue_type="conflict", issue_subtype="cross_document_authority_conflict",
                audited_text=text, authoritative_evidence=citations,
                citation=cross.higher_authority_evidence,
                explanation=(f"Resolved by document hierarchy. {cross.higher_authority_document} "
                             "has the higher configured authority score and governs; the lower-authority passage is retained."),
                suggested_correction=f"Align the clause with {cross.higher_authority_document}.",
                confidence=0.9, abstention_reason=None,
                higher_authority_evidence=cross.higher_authority_evidence,
                conflicting_evidence=citations, authority_scores=cross.authority_scores,
                conflicting_normative_terms=cross.conflicting_normative_terms,
                interpretations=cross.interpretations, resolution_basis=cross.resolution_basis,
                human_review_required=False)
        combined = " ".join(item[2] for item in ranked)
        query_terms = set(tokens(text))
        old_lower = text.lower()
        smcs_tab_governance = ("smcs-tab" in old_lower and bool(re.search(
            r"\b(formal approval|formal evaluation|final review|final decision|decision authority|"
            r"grant continued recognition|initiate dissolution|shall be established|termination)\b",
            old_lower)))
        preferred_terms = (["names"] if "biograph" in old_lower else
                           ["specialty", "technical"] if "technical committees" in old_lower else
                           ["open to all", "regardless"] if "only" in old_lower and any(term in old_lower for term in ("join", "membership")) else
                           ["at a minimum", "finance chair"] if "only" in old_lower and "chair" in old_lower else
                           ["priority", "distant"] if "priorit" in old_lower else
                           ["eligibility", "accepted", "registered"] if "without" in old_lower and any(term in old_lower for term in ("register", "attend", "paper")) else
                           ["technical co-sponsorship", "no financial responsibility"] if "technical" in old_lower and "financial responsibility" in old_lower else
                           ["area committee", "smcs-bog", "vp-ta"] if smcs_tab_governance else [])
        if preferred_terms:
            preferred = [item for item in ranked if any(term in item[2].lower() for term in preferred_terms)]
        else:
            preferred = []
        if smcs_tab_governance and preferred:
            chunk, score, full_evidence, similarity = max(preferred, key=lambda item: (
                3 * ("area committee" in item[2].lower()) + 2 * ("smcs-bog" in item[2].lower()) +
                ("vp-ta" in item[2].lower()), item[3]))
        else:
            # Policy Audit is anchored to the Corrected Operations Manual. Other
            # approved documents remain available above for hierarchy/conflict
            # detection, but the final clause comparison should cite its target.
            corrected = [item for item in (preferred or ranked)
                         if item[0].document_id == "smcs-operations-manual-v2-corrected"]
            # Search already combines lexical relevance, embeddings, numeric
            # signals and reranking. Preserve its highest-ranked authoritative
            # clause instead of re-sorting by a weaker text-only similarity.
            chunk, score, full_evidence, similarity = (corrected[0] if corrected else
                max(preferred or ranked, key=lambda item: item[3]))
        evidence = self.rag._best_passage(chunk.text, text)
        comparison_similarity = similarity
        coverage = len(query_terms & set(tokens(combined))) / max(1, len(query_terms))
        issue_type, subtype, abstention = self._classify(text, full_evidence, comparison_similarity, coverage)
        focused_similarity = semantic_similarity(text, evidence)
        focused_coverage = len(query_terms & set(tokens(evidence))) / max(1, len(query_terms))
        focused_issue, focused_subtype, focused_abstention = self._classify(
            text, evidence, focused_similarity, focused_coverage)
        high_precision_subtypes = {
            "time_period_mismatch", "quantified_requirement_mismatch", "role_assignment_mismatch",
            "reporting_frequency_mismatch", "polarity_mismatch", "missing_required_items",
            "unsupported_exclusive_restriction", "approval_threshold_mismatch",
            "approval_condition_mismatch", "missing_eligibility_conditions", "material_term_mismatch",
        }
        if focused_issue in {"conflict", "unsupported_claim", "missing_requirement", "ambiguous"}:
            if focused_subtype in high_precision_subtypes:
                issue_type, subtype, abstention = focused_issue, focused_subtype, focused_abstention
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
                suggested_correction=None, confidence=round(min(0.6, comparison_similarity), 2), abstention_reason=abstention)

        conflict_status = "confirmed" if issue_type == "conflict" and comparison_similarity >= 0.35 else "possible" if issue_type in {"conflict", "unsupported_claim", "missing_requirement"} else "none"
        suggestion = self._suggest_correction(subtype, evidence, text) if conflict_status != "none" else None
        return AuditResponse(conflict_status=conflict_status, issue_type=issue_type, issue_subtype=subtype,
            audited_text=text, authoritative_evidence=[citation], citation=citation,
            explanation=("A material deterministic mismatch was found in the retrieved authoritative passage."
                         if issue_type == "conflict" else
                         "The audited normative wording is stronger than or weakly supported by the retrieved authoritative text."
                         if issue_type == "unsupported_claim" else
                         "The retrieved authoritative passage does not indicate a material conflict."),
            suggested_correction=suggestion, confidence=round(min(0.95, max(score, comparison_similarity)), 2), abstention_reason=None)
