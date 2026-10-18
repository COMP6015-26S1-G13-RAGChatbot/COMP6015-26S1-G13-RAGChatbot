from __future__ import annotations

import hashlib
from collections import OrderedDict

import httpx
import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from backend.core.config import Config


class EmbeddingService:
    """Offline-first semantic embeddings using local LSA or an explicitly configured transformer."""

    _cache: dict[tuple[str, str, str], tuple] = {}
    _query_cache: OrderedDict[tuple[str, str, str, str], list[float]] = OrderedDict()

    def __init__(self, texts: list[str], backend: str | None = None):
        self.backend = backend or Config.EMBEDDING_BACKEND
        self._corpus_digest = hashlib.sha256("\0".join(texts).encode("utf-8")).hexdigest()
        self.model_name = Config.EMBEDDING_MODEL
        self._model = None
        self._vectorizer = None
        self._svd = None
        self._ollama_url = Config.OLLAMA_BASE_URL
        if self.backend == "ollama":
            self.model_name = (self.model_name if not self.model_name.startswith("sentence-transformers/")
                               else "nomic-embed-text:latest")
            digest = hashlib.sha256("\0".join(texts).encode("utf-8")).hexdigest()
            cache_key = (self.backend, self.model_name, digest)
            if cache_key in self._cache:
                self.document_vectors = self._cache[cache_key][0]
                return
            vectors = []
            try:
                for start in range(0, len(texts), 64):
                    response = httpx.post(f"{self._ollama_url}/api/embed", json={
                        "model": self.model_name, "input": texts[start:start + 64], "truncate": True,
                    }, timeout=180.0)
                    response.raise_for_status()
                    vectors.extend(response.json()["embeddings"])
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                raise RuntimeError(
                    f"Configured Ollama embedding model is unavailable: {self.model_name}") from exc
            self.document_vectors = normalize(np.asarray(vectors, dtype=float))
            self._cache[cache_key] = (self.document_vectors,)
            return
        if self.backend == "sentence_transformer":
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name, local_files_only=True)
                self.backend = "sentence_transformer"
                self.document_vectors = np.asarray(
                    self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
                )
                return
            except Exception as exc:
                raise RuntimeError(f"Configured embedding model is unavailable locally: {self.model_name}") from exc
        self.backend = "local_lsa"
        self.model_name = "tfidf-truncated-svd-128-v1"
        digest = hashlib.sha256("\0".join(texts).encode("utf-8")).hexdigest()
        cache_key = (self.backend, self.model_name, digest)
        if cache_key in self._cache:
            self._vectorizer, self._svd, self.document_vectors = self._cache[cache_key]
            return
        self._vectorizer = TfidfVectorizer(
            analyzer="word", ngram_range=(1, 2), min_df=1, sublinear_tf=True, norm="l2",
            stop_words="english"
        )
        sparse = self._vectorizer.fit_transform(texts)
        dimensions = max(2, min(128, sparse.shape[0] - 1, sparse.shape[1] - 1))
        self._svd = TruncatedSVD(n_components=dimensions, random_state=0)
        self.document_vectors = normalize(self._svd.fit_transform(sparse))
        self._cache[cache_key] = (self._vectorizer, self._svd, self.document_vectors)

    @property
    def configuration(self) -> dict[str, str]:
        return {"backend": self.backend, "model": self.model_name}

    def similarities(self, query: str) -> list[float]:
        query_key = (self.backend, self.model_name, self._corpus_digest,
                     hashlib.sha256(query.encode("utf-8")).hexdigest())
        cached = self._query_cache.get(query_key)
        if cached is not None:
            self._query_cache.move_to_end(query_key)
            return list(cached)
        if self.backend == "ollama":
            try:
                response = httpx.post(f"{self._ollama_url}/api/embed", json={
                    "model": self.model_name, "input": query, "truncate": True,
                }, timeout=60.0)
                response.raise_for_status()
                query_vector = normalize(np.asarray(response.json()["embeddings"], dtype=float))[0]
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                raise RuntimeError(f"Ollama query embedding failed: {self.model_name}") from exc
            scores = np.dot(self.document_vectors, query_vector).clip(0, 1).tolist()
            self._remember_query(query_key, scores)
            return scores
        if self._model is not None:
            query_vector = np.asarray(
                self._model.encode([query], normalize_embeddings=True, show_progress_bar=False)
            )[0]
            scores = np.dot(self.document_vectors, query_vector).clip(0, 1).tolist()
            self._remember_query(query_key, scores)
            return scores
        query_vector = normalize(self._svd.transform(self._vectorizer.transform([query])))
        scores = np.asarray(self.document_vectors @ query_vector.T).ravel().clip(0, 1).tolist()
        self._remember_query(query_key, scores)
        return scores

    @classmethod
    def _remember_query(cls, key: tuple[str, str, str, str], scores: list[float]) -> None:
        cls._query_cache[key] = list(scores)
        cls._query_cache.move_to_end(key)
        while len(cls._query_cache) > 128:
            cls._query_cache.popitem(last=False)
