import re

from backend.core.config import Config
from backend.models import ChatResponse, Citation, Conflict
from backend.services.search_service import SearchService, semantic_similarity, tokens


SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


class RAGService:
    def __init__(self, search: SearchService | None = None):
        self.search = search or SearchService()

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
                        section=section, page=chunk.page, evidence_text=evidence)

    @staticmethod
    def validate_citations(citations: list[Citation], retrieved) -> list[Citation]:
        evidence = {(chunk.document_id, chunk.page, " ".join(chunk.text.split())) for chunk, _ in retrieved}
        return [citation for citation in citations if any(
            citation.document_id == doc_id and citation.page == page and
            " ".join(citation.evidence_text.split()) in text for doc_id, page, text in evidence)]

    @staticmethod
    def _genuine_conflict(high_ev: str, low_ev: str) -> bool:
        if semantic_similarity(high_ev, low_ev) < 0.5:
            return False
        high_days = set(re.findall(r"\b(\d+)\s+days?\b", high_ev.lower()))
        low_days = set(re.findall(r"\b(\d+)\s+days?\b", low_ev.lower()))
        term_conflict = (("biograph" in high_ev.lower()) != ("biograph" in low_ev.lower()) and
                         "candidate" in high_ev.lower() and "candidate" in low_ev.lower())
        return bool((high_days and low_days and high_days != low_days) or term_conflict)

    def answer(self, question: str) -> ChatResponse:
        retrieved = self.search.search(question)
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
            if semantic_similarity(primary_evidence, evidence) < 0.55:
                continue
            if any(semantic_similarity(evidence, prior[2]) >= 0.9 for prior in supporting):
                continue
            supporting.append((chunk, score, evidence))

        citations = self.validate_citations(
            [self._citation(chunk, evidence) for chunk, _, evidence in supporting], retrieved)
        if not citations:
            return ChatResponse(answer="I cannot provide a validated citation for the retrieved material.", citations=[],
                conflict_status="none", conflicts=[], confidence=0.0, abstained=True,
                abstention_reason="Citation validation failed.")

        conflicts: list[Conflict] = []
        for chunk, _, evidence in supporting[1:]:
            if chunk.document_id == primary_chunk.document_id or not self._genuine_conflict(primary_evidence, evidence):
                continue
            high_chunk, high_ev, low_chunk, low_ev = (primary_chunk, primary_evidence, chunk, evidence)
            if chunk.authority_level > primary_chunk.authority_level:
                high_chunk, high_ev, low_chunk, low_ev = chunk, evidence, primary_chunk, primary_evidence
            conflicts.append(Conflict(topic=question, lower_authority_document=low_chunk.document_title,
                higher_authority_document=high_chunk.document_title, lower_authority_evidence=low_ev,
                higher_authority_evidence=high_ev,
                applied_rule="The approved Corrected Operations Manual has the configured highest authority and controls genuinely incompatible claims."))

        if conflicts:
            supporting.sort(key=lambda item: item[0].authority_level, reverse=True)
            citations = self.validate_citations(
                [self._citation(chunk, evidence) for chunk, _, evidence in supporting], retrieved)
            answer = f"Possible disagreement detected. Applying the configured authority rule: {supporting[0][2]} [1]"
        else:
            answer = f"{primary_evidence} [1]"
        return ChatResponse(answer=answer, citations=citations, conflict_status="possible" if conflicts else "none",
            conflicts=conflicts, confidence=min(0.95, round(primary_score, 2)), abstained=False)
