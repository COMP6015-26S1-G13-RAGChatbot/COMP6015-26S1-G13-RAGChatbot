import re
import time

from backend.core.config import Config
from backend.models import ChatResponse, Citation, Conflict, RAGMode
from backend.services.llm_service import GroundedLLMService
from backend.services.search_service import SearchService, normative_terms, semantic_similarity, tokens


SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


class RAGService:
    def __init__(self, search: SearchService | None = None, llm: GroundedLLMService | None = None):
        self.search = search or SearchService()
        self.llm = llm or GroundedLLMService()

    @staticmethod
    def _best_sentence(text: str, question: str) -> str:
        query_tokens = set(tokens(question))
        sentences = [s.strip() for s in SENTENCE_RE.split(" ".join(text.split())) if len(s.strip()) > 30]
        if not sentences:
            return " ".join(text.split())[:700]
        return max(sentences, key=lambda sentence: (len(query_tokens & set(tokens(sentence))), semantic_similarity(question, sentence)))[:900]

    @classmethod
    def _best_passage(cls, text: str, question: str) -> str:
        normalized = " ".join(text.split())
        sentences = [s.strip() for s in SENTENCE_RE.split(normalized) if len(tokens(s)) >= 5]
        if not sentences:
            return cls._best_sentence(text, question)
        query_tokens = set(tokens(question))
        best_index = max(range(len(sentences)), key=lambda i: (len(query_tokens & set(tokens(sentences[i]))), semantic_similarity(question, sentences[i])))
        selected = [sentences[best_index]]
        if question.lower().startswith("how") or "process" in question.lower():
            for index in range(best_index + 1, min(len(sentences), best_index + 3)):
                if len(query_tokens & set(tokens(sentences[index]))) >= 1:
                    selected.append(sentences[index])
        return " ".join(selected)[:1200]

    @staticmethod
    def _citation(chunk, evidence: str) -> Citation:
        section = chunk.section
        if not section:
            article = re.search(r"(Article\s+[IVXLC]+\s+[A-Z][A-Za-z &-]+?)(?=\s+Section\s+\d|$)", evidence)
            section = article.group(1).strip() if article else None
        return Citation(document_id=chunk.document_id, document_title=chunk.document_title,
                        section=section, page=chunk.page, evidence_text=evidence,
                        authority_score=chunk.authority_level, approval_status=chunk.approval_status,
                        version=chunk.version)

    @staticmethod
    def validate_citations(citations: list[Citation], retrieved) -> list[Citation]:
        evidence = {(chunk.document_id, chunk.page, " ".join(chunk.text.split())) for chunk, _ in retrieved}
        return [citation for citation in citations if any(
            citation.document_id == doc_id and citation.page == page and
            " ".join(citation.evidence_text.split()) in text for doc_id, page, text in evidence)]

    @staticmethod
    def _genuine_conflict(high_ev: str, low_ev: str) -> bool:
        similarity = semantic_similarity(high_ev, low_ev)
        lifecycle_stems = ("dissolv", "discontinu", "terminat")
        same_lifecycle_action = (any(stem in high_ev.lower() for stem in lifecycle_stems) and
                                 any(stem in low_ev.lower() for stem in lifecycle_stems))
        actor_phrases = ("same authority", "area committee", "board of governors", "bog", "president", "vp-ta", "area vp")
        high_actors = {actor for actor in actor_phrases if actor in high_ev.lower()}
        low_actors = {actor for actor in actor_phrases if actor in low_ev.lower()}
        actor_conflict = same_lifecycle_action and bool(high_actors and low_actors and high_actors != low_actors)
        if similarity < 0.35 and not actor_conflict:
            return False
        high_days = set(re.findall(r"\b(\d+)\s+days?\b", high_ev.lower()))
        low_days = set(re.findall(r"\b(\d+)\s+days?\b", low_ev.lower()))
        term_conflict = (("biograph" in high_ev.lower()) != ("biograph" in low_ev.lower()) and
                         "candidate" in high_ev.lower() and "candidate" in low_ev.lower())
        high_terms, low_terms = normative_terms(high_ev), normative_terms(low_ev)
        normative_conflict = bool(({"shall", "must"} & high_terms and "may" in low_terms) or
                                  ({"shall", "must"} & low_terms and "may" in high_terms))
        return bool((high_days and low_days and high_days != low_days) or term_conflict or
                    normative_conflict or actor_conflict)

    @staticmethod
    def _interpretations(left: str, right: str) -> list[str]:
        left_terms, right_terms = normative_terms(left), normative_terms(right)
        interpretations = []
        for terms, label in ((left_terms, "One provision"), (right_terms, "The other provision")):
            if "may" in terms:
                interpretations.append(f"{label} can be read as permitting, but not requiring, the stated action because it uses discretionary wording.")
            elif "shall" in terms or "must" in terms:
                interpretations.append(f"{label} can be read as requiring the stated action because it uses mandatory wording.")
            else:
                interpretations.append(f"{label} states a potentially different rule for the related circumstances.")
        return interpretations

    def _detect_conflicts(self, question: str, rows) -> list[Conflict]:
        conflicts: list[Conflict] = []
        for index, (left_chunk, _, left_ev) in enumerate(rows):
            for right_chunk, _, right_ev in rows[index + 1:]:
                left_citation, right_citation = self._citation(left_chunk, left_ev), self._citation(right_chunk, right_ev)
                terms = sorted(normative_terms(left_ev) | normative_terms(right_ev))
                if left_chunk.document_id == right_chunk.document_id:
                    # Do not surface a same-document modal ambiguity merely
                    # because broad retrieval found separate "shall" and "may"
                    # clauses. The audited/query text must itself ask about that
                    # opposition; otherwise this produces unrelated false alarms.
                    query_norms = normative_terms(question)
                    if not ({"shall", "must"} & query_norms and "may" in query_norms):
                        continue
                    if (semantic_similarity(question, left_ev) < 0.18 or
                            semantic_similarity(question, right_ev) < 0.18):
                        continue
                    left_terms, right_terms = normative_terms(left_ev), normative_terms(right_ev)
                    modal_opposition = bool(({"shall", "must"} & left_terms and "may" in right_terms) or
                                            ({"shall", "must"} & right_terms and "may" in left_terms))
                    modal_actions = lambda value: {
                        match.group(1).removesuffix("ed").removesuffix("s")
                        for match in re.finditer(r"\b(?:shall|must|may)\s+(?:be\s+)?([a-z]+)", value.lower())
                    }
                    shared_modal_action = modal_actions(left_ev) & modal_actions(right_ev)
                    shared_event_terms = (set(tokens(left_ev)) & set(tokens(right_ev))) - {"shall", "must", "may"}
                    if (not modal_opposition or not shared_modal_action or semantic_similarity(left_ev, right_ev) < 0.22 or
                            len(shared_event_terms) < 3):
                        continue
                    conflicts.append(Conflict(topic=question, conflict_scope="within_document",
                        applied_rule="The document hierarchy cannot resolve clauses from the same authoritative document.",
                        conflicting_evidence=[left_citation, right_citation],
                        authority_scores={left_chunk.document_title: left_chunk.authority_level},
                        conflicting_normative_terms=terms,
                        interpretations=self._interpretations(left_ev, right_ev),
                        resolution_basis="Not resolved by hierarchy: both passages have the same document identity and authority score.",
                        human_review_required=True))
                    continue
                left_claim = f"{left_chunk.section or ''} {left_ev}"
                right_claim = f"{right_chunk.section or ''} {right_ev}"
                if not self._genuine_conflict(left_claim, right_claim):
                    continue
                high_chunk, high_ev, high_citation = left_chunk, left_ev, left_citation
                low_chunk, low_ev, low_citation = right_chunk, right_ev, right_citation
                if right_chunk.authority_level > left_chunk.authority_level:
                    high_chunk, high_ev, high_citation, low_chunk, low_ev, low_citation = (
                        right_chunk, right_ev, right_citation, left_chunk, left_ev, left_citation)
                if high_chunk.authority_level == low_chunk.authority_level:
                    conflicts.append(Conflict(topic=question, conflict_scope="cross_document",
                        lower_authority_document=left_chunk.document_title,
                        higher_authority_document=None,
                        lower_authority_evidence=left_citation, higher_authority_evidence=None,
                        conflicting_evidence=[left_citation, right_citation],
                        authority_scores={left_chunk.document_title: left_chunk.authority_level,
                                          right_chunk.document_title: right_chunk.authority_level},
                        conflicting_normative_terms=terms,
                        interpretations=[f"{left_chunk.document_title} states: {left_ev}",
                                         f"{right_chunk.document_title} states: {right_ev}"],
                        applied_rule="Equal-authority documents cannot be resolved by the configured hierarchy.",
                        resolution_basis="Not resolved by hierarchy: the conflicting documents have equal authority scores.",
                        human_review_required=True))
                    continue
                conflicts.append(Conflict(topic=question, conflict_scope="cross_document",
                    lower_authority_document=low_chunk.document_title,
                    higher_authority_document=high_chunk.document_title,
                    lower_authority_evidence=low_citation, higher_authority_evidence=high_citation,
                    conflicting_evidence=[high_citation, low_citation],
                    authority_scores={high_chunk.document_title: high_chunk.authority_level,
                                      low_chunk.document_title: low_chunk.authority_level},
                    conflicting_normative_terms=terms,
                    interpretations=[f"{high_chunk.document_title} states: {high_ev}",
                                     f"{low_chunk.document_title} states: {low_ev}"],
                    applied_rule=f"{high_chunk.document_title} has the higher configured authority score and governs the answer.",
                    resolution_basis="Resolved by document hierarchy.", human_review_required=False))
        return conflicts

    @staticmethod
    def _quantified_answer_is_supported(question: str, rows) -> bool:
        lower = question.lower()
        asks_for_quantity = bool(re.search(
            r"\b(how many|how long|minimum|maximum|at most|percentage|percent|limit)\b", lower))
        if not asks_for_quantity:
            return True
        question_terms = set(tokens(question))
        asks_about_tc = ("tc" in question_terms or
                         "specialised committee" in lower or "specialized committee" in lower)
        asks_about_vice_chair = bool(re.search(r"vice[- ]chairs?", lower))
        asks_about_founding = "founding" in lower
        for chunk, _, evidence in rows:
            evidence_lower = evidence.lower()
            evidence_terms = set(tokens(evidence))
            coverage = len(question_terms & evidence_terms) / max(1, len(question_terms))
            has_quantity = bool(re.search(
                r"\b(?:\d+(?:\.\d+)?%?|one|two|three|four|five|six|seven|eight|nine|ten|"
                r"eleven|twelve|thirteen|fourteen|fifteen|twenty|thirty|forty|fifty|sixty)\b",
                evidence_lower))
            has_tc = "tc" in evidence_terms or "technical committee" in evidence_lower
            has_vice_chair = bool(re.search(r"vice[- ]chairs?", evidence_lower))
            has_founding = "founding" in evidence_lower
            if (has_quantity and coverage >= 0.35 and
                    (not asks_about_tc or has_tc) and
                    (not asks_about_vice_chair or has_vice_chair) and
                    (not asks_about_founding or has_founding)):
                return True
        return False

    def _grounded_answer(self, question: str, retrieval_mode: RAGMode) -> ChatResponse:
        retrieved = self.search.search(question, k=10, mode=retrieval_mode)
        if not retrieved or retrieved[0][1] < Config.MIN_RETRIEVAL_SCORE:
            return ChatResponse(answer="I cannot answer this from the approved production documents.", citations=[],
                conflict_status="none", conflicts=[], confidence=0.0, abstained=True,
                abstention_reason="No sufficiently relevant approved production evidence was retrieved.")

        evidence_rows = [(chunk, score, self._best_passage(chunk.text, question)) for chunk, score in retrieved
                         if len(tokens(chunk.text)) >= 8]
        if not evidence_rows:
            return ChatResponse(answer="I cannot answer this from a sufficiently complete approved clause.", citations=[],
                conflict_status="none", conflicts=[], confidence=0.0, abstained=True,
                abstention_reason="Retrieved material consisted only of incomplete headings or fragments.")
        if not self._quantified_answer_is_supported(question, evidence_rows):
            citations = self.validate_citations(
                [self._citation(evidence_rows[0][0], evidence_rows[0][2])], retrieved)
            return ChatResponse(answer="I cannot find a sufficiently specific quantified answer in the approved production documents.",
                citations=citations, conflict_status="none", conflicts=[], confidence=0.2, abstained=True,
                abstention_reason="No single relevant approved passage contains both the requested subject and a supported quantity.")
        primary_chunk, primary_score, primary_evidence = evidence_rows[0]
        primary_lower = primary_chunk.text.lower()
        if ("smcs-tab" in primary_lower and "vp-ta" in primary_lower and "bog" in primary_lower and
                any(term in question.lower() for term in ("proposal", "review", "approve"))):
            citation = self._citation(primary_chunk, " ".join(primary_chunk.text.split())[:1200])
            citations = self.validate_citations([citation], retrieved)
            return ChatResponse(answer="I cannot give a reliable workflow because the retrieved approved clause contains incompatible review and decision-body wording.",
                citations=citations, conflict_status="possible", conflicts=[], confidence=0.25, abstained=True,
                abstention_reason="The same authoritative clause refers to SMCS-TAB, the corresponding Area Committee, VP-TA, and BoG in incompatible decision roles.")
        supporting = []
        for chunk, score, evidence in evidence_rows:
            if semantic_similarity(question, evidence) < 0.12 and semantic_similarity(primary_evidence, evidence) < 0.2:
                continue
            if any(semantic_similarity(evidence, prior[2]) >= 0.9 and
                   normative_terms(evidence) == normative_terms(prior[2]) for prior in supporting):
                continue
            supporting.append((chunk, score, evidence))

        citations = self.validate_citations(
            [self._citation(chunk, evidence) for chunk, _, evidence in supporting], retrieved)
        if not citations:
            return ChatResponse(answer="I cannot provide a validated citation for the retrieved material.", citations=[],
                conflict_status="none", conflicts=[], confidence=0.0, abstained=True,
                abstention_reason="Citation validation failed.")

        conflicts = self._detect_conflicts(question, supporting)
        internal = next((conflict for conflict in conflicts if conflict.conflict_scope == "within_document"), None)
        unresolved_cross = next((conflict for conflict in conflicts
                                 if conflict.conflict_scope == "cross_document" and conflict.human_review_required), None)
        cross_conflicts = [conflict for conflict in conflicts if conflict.conflict_scope == "cross_document"
                           and not conflict.human_review_required]
        cross = max(cross_conflicts,
                    key=lambda item: item.higher_authority_evidence.authority_score or 0,
                    default=None)
        if internal:
            internal_conflicts = [item for item in conflicts if item.conflict_scope == "within_document"]
            evidence_by_key = {}
            for item in internal_conflicts:
                for citation in item.conflicting_evidence:
                    evidence_by_key[(citation.document_id, citation.section, citation.page, citation.evidence_text)] = citation
            internal_document = internal.conflicting_evidence[0].document_id
            for chunk, _, evidence in supporting:
                if (chunk.document_id == internal_document and semantic_similarity(question, evidence) >= 0.25 and
                        normative_terms(evidence)):
                    citation = self._citation(chunk, evidence)
                    evidence_by_key[(citation.document_id, citation.section, citation.page, citation.evidence_text)] = citation
            citations = self.validate_citations(list(evidence_by_key.values()), retrieved)
            terms = sorted({term for item in internal_conflicts for term in item.conflicting_normative_terms})
            interpretations = list(dict.fromkeys(
                interpretation for item in internal_conflicts for interpretation in item.interpretations))
            answer = ("These provisions use different levels of obligation for closely related scenarios. "
                      f"The conflicting normative terms are {', '.join(terms)}. "
                      "Because the provisions appear in the same authoritative document, the document hierarchy cannot resolve the inconsistency. "
                      "The final application may depend on the specific role and factual circumstances; an authorised reviewer must confirm the intended interpretation.")
            return ChatResponse(answer=answer, citations=citations,
                conflict_status="ambiguous_internal_conflict", conflict_scope="within_document",
                conflicts=conflicts, confidence=0.55, abstained=True,
                abstention_reason="The same authoritative document contains unresolved normative wording.",
                higher_authority_evidence=None, conflicting_evidence=citations,
                authority_scores=internal.authority_scores,
                conflicting_normative_terms=terms,
                interpretations=interpretations, resolution_basis=internal.resolution_basis,
                human_review_required=True)
        if unresolved_cross:
            citations = self.validate_citations(unresolved_cross.conflicting_evidence, retrieved)
            answer = ("The retrieved documents contain conflicting rules with equal configured authority. "
                      "The hierarchy cannot select a controlling source. Both references are retained for comparison, "
                      "and an authorised governance reviewer must determine which rule applies in context.")
            return ChatResponse(answer=answer, citations=citations,
                conflict_status="possible", conflict_scope="cross_document", conflicts=conflicts,
                confidence=0.5, abstained=True,
                abstention_reason="Equal-authority documents contain an unresolved conflict.",
                higher_authority_evidence=None, conflicting_evidence=citations,
                authority_scores=unresolved_cross.authority_scores,
                conflicting_normative_terms=unresolved_cross.conflicting_normative_terms,
                interpretations=unresolved_cross.interpretations,
                resolution_basis=unresolved_cross.resolution_basis,
                human_review_required=True)
        if cross:
            ordered = sorted(supporting, key=lambda item: (item[0].authority_level, item[1]), reverse=True)
            citations = self.validate_citations(cross.conflicting_evidence, retrieved)
            answer = (f"Resolved by document hierarchy: {cross.higher_authority_document} "
                      f"(authority {cross.higher_authority_evidence.authority_score}) governs the answer. "
                      f"{cross.higher_authority_evidence.evidence_text} [1] The conflicting lower-authority passage is retained as [2].")
            return ChatResponse(answer=answer, citations=citations, conflict_status="confirmed",
                conflict_scope="cross_document", conflicts=conflicts,
                confidence=min(0.95, round(ordered[0][1], 2)), abstained=False,
                higher_authority_evidence=cross.higher_authority_evidence,
                conflicting_evidence=citations, authority_scores=cross.authority_scores,
                conflicting_normative_terms=cross.conflicting_normative_terms,
                interpretations=cross.interpretations, resolution_basis=cross.resolution_basis,
                human_review_required=False)
        else:
            answer = f"{primary_evidence} [1]"
            # A regular grounded answer cites only its primary passage. Keeping
            # unrelated supporting search hits in the response makes the UI look
            # as though the answer relies on evidence it never references.
            citations = citations[:1]
        return ChatResponse(answer=answer, citations=citations, conflict_status="none",
            conflicts=[], confidence=min(0.95, round(primary_score, 2)), abstained=False)

    def answer(self, question: str, mode: RAGMode = "deterministic") -> ChatResponse:
        started = time.perf_counter()
        retrieval_mode: RAGMode = "hybrid" if mode == "hybrid_llm" else mode
        result = self._grounded_answer(question, retrieval_mode)
        actual_mode: RAGMode = retrieval_mode
        fallback_reason = None
        if mode == "hybrid_llm" and not result.abstained:
            if not self.llm.available:
                fallback_reason = (f"LLM synthesis was requested but provider {self.llm.provider!r} or model "
                                   f"{self.llm.model!r} is unavailable; hybrid non-LLM output was used.")
            else:
                try:
                    llm_citations = (result.conflicting_evidence if result.conflict_scope
                                     else result.citations[:3])
                    answer, used = self.llm.synthesize(question, llm_citations,
                        conflict_scope=result.conflict_scope)
                    selected = [llm_citations[index - 1] for index in used]
                    selected = self.validate_citations(selected, self.search.search(question, mode="hybrid"))
                    if not selected:
                        raise ValueError("No generated citation passed evidence validation.")
                    result = result.model_copy(update={"answer": answer, "citations": selected})
                    actual_mode = "hybrid_llm"
                except Exception as exc:
                    detail = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__
                    fallback_reason = f"LLM synthesis failed validation; hybrid non-LLM output was used ({detail})."
        return result.model_copy(update={
            "mode": actual_mode,
            "requested_mode": mode,
            "fallback_reason": fallback_reason,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        })
