import json
import math
import re
from collections import Counter
from difflib import SequenceMatcher

from backend.core.config import Config
from backend.services.ingest_service import IngestService, SectionChunk
from backend.services.registry_service import RegistryService


TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {"a", "an", "and", "are", "as", "at", "be", "by", "does", "for", "from", "how", "in", "is", "of", "on", "or", "the", "to", "what", "when", "who", "with"}


def tokens(text: str) -> list[str]:
    raw = TOKEN_RE.findall(text.lower())
    normalized = []
    for token in raw:
        if token in STOPWORDS or len(token) <= 1:
            continue
        token = {"attendance": "attend", "attending": "attend", "attended": "attend",
                 "available": "offer", "offers": "offer", "offered": "offer"}.get(token, token)
        if token.endswith("ies") and len(token) > 5:
            token = token[:-3] + "y"
        elif token.endswith("s") and len(token) > 4 and token != "smcs":
            token = token[:-1]
        normalized.append(token)
    if "technical committee" in text.lower() and "tc" not in normalized:
        normalized.append("tc")
    return normalized


def semantic_similarity(left: str, right: str) -> float:
    left_tokens, right_tokens = set(tokens(left)), set(tokens(right))
    jaccard = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    sequence = SequenceMatcher(None, " ".join(tokens(left)), " ".join(tokens(right))).ratio()
    return 0.65 * jaccard + 0.35 * sequence


class SearchService:
    def __init__(self, registry: RegistryService | None = None, chunks: list[SectionChunk] | None = None):
        self.registry = registry or RegistryService()
        if chunks is not None:
            self.chunks = chunks
        elif Config.INDEX_PATH.exists():
            self.chunks = [SectionChunk(**item) for item in json.loads(Config.INDEX_PATH.read_text(encoding="utf-8"))]
        else:
            self.chunks = IngestService(self.registry).build()

    @staticmethod
    def _scores(query: str, chunk: SectionChunk) -> tuple[float, float]:
        query_counts = Counter(tokens(query))
        chunk_counts = Counter(tokens(f"{chunk.section or ''} {chunk.text}"))
        overlap = sum(min(count, chunk_counts[token]) for token, count in query_counts.items())
        if not overlap:
            return 0.0, 0.0
        coverage = overlap / max(1, sum(query_counts.values()))
        density = overlap / math.sqrt(max(1, sum(chunk_counts.values())))
        sentence_scores = []
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", chunk.text):
            counts = Counter(tokens(sentence))
            sentence_overlap = sum(min(count, counts[token]) for token, count in query_counts.items())
            if sentence_overlap:
                sentence_scores.append(sentence_overlap / max(1, sum(query_counts.values())))
        sentence_coverage = max(sentence_scores, default=0)
        lexical = coverage * 0.48 + sentence_coverage * 0.42 + density * 0.10
        rerank = lexical * 0.72 + semantic_similarity(query, chunk.text) * 0.18 + sentence_coverage * 0.10
        return lexical, rerank

    def debug_search(self, query: str, k: int = Config.MAX_RESULTS, *, document_ids: set[str] | None = None) -> list[dict]:
        production = {doc.document_id for doc in self.registry.production_documents()}
        requested = production if document_ids is None else production & document_ids
        candidates = []
        for chunk in self.chunks:
            lexical, rerank = self._scores(query, chunk)
            if chunk.document_id not in production:
                included, reason = False, "excluded: document is not approved retrieval-enabled production content"
            elif chunk.document_id not in requested:
                included, reason = False, "excluded: document does not match the requested metadata filter"
            elif lexical <= 0:
                included, reason = False, "excluded: no lexical term overlap"
            else:
                included, reason = True, "included: passed production metadata filter and relevance threshold"
            if lexical > 0 or chunk.document_id not in production:
                candidates.append({"chunk": chunk, "lexical_score": lexical, "reranking_score": rerank,
                                   "included": included, "reason": reason})
        candidates.sort(key=lambda item: (item["included"], item["reranking_score"], item["chunk"].authority_level), reverse=True)
        included_count = 0
        output = []
        for item in candidates:
            if item["included"]:
                included_count += 1
                if included_count > k:
                    item = {**item, "included": False, "reason": f"excluded: ranked below top {k}"}
            output.append(item)
        # Debug output stays bounded while retaining representative exclusion reasons.
        included = [item for item in output if item["included"]]
        excluded = [item for item in output if not item["included"]][:max(5, k)]
        return included + excluded

    def search(self, query: str, k: int = Config.MAX_RESULTS, *, document_ids: set[str] | None = None) -> list[tuple[SectionChunk, float]]:
        return [(item["chunk"], item["reranking_score"]) for item in self.debug_search(query, k, document_ids=document_ids) if item["included"]]
