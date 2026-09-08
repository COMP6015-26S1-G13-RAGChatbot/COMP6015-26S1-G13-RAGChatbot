from __future__ import annotations

import json
import os
import re

import httpx

from backend.core.config import Config
from backend.models import Citation, ConflictScope


class GroundedLLMService:
    """Optional synthesis over retrieved production evidence only."""

    def __init__(self, client=None):
        self.model = Config.LLM_MODEL
        self.provider = Config.LLM_PROVIDER
        self._client = client
        self._ollama_available = False
        if self._client is None and os.getenv("OPENAI_API_KEY") and self.provider == "openai":
            from openai import OpenAI
            self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        if self.provider == "ollama":
            try:
                response = httpx.get(f"{Config.OLLAMA_BASE_URL}/api/tags", timeout=2.0)
                response.raise_for_status()
                installed = {item.get("name") for item in response.json().get("models", [])}
                self._ollama_available = self.model in installed
            except (httpx.HTTPError, ValueError):
                self._ollama_available = False

    @property
    def available(self) -> bool:
        if self.provider == "ollama":
            return self._ollama_available
        return self.provider == "openai" and self._client is not None

    @property
    def configuration(self) -> dict[str, str | bool]:
        return {"provider": self.provider, "model": self.model, "available": self.available}

    def synthesize(self, question: str, citations: list[Citation],
                   conflict_scope: ConflictScope | None = None) -> tuple[str, list[int]]:
        if not self.available:
            reason = (f"Ollama model {self.model!r} is not available at {Config.OLLAMA_BASE_URL}."
                      if self.provider == "ollama" else "No configured OpenAI API key is available.")
            raise RuntimeError(reason)
        evidence = "\n\n".join(
            f"[{index}] document={item.document_title}; version={item.version}; approval={item.approval_status}; "
            f"authority={item.authority_score}; section={item.section or 'section unavailable'}; page={item.page}:\n{item.evidence_text}"
            for index, item in enumerate(citations, start=1)
        )
        prompt = f"""Answer the question using only EVIDENCE below. Do not use outside knowledge.
If the evidence is insufficient, return an empty answer. Keep the answer concise.
Every factual sentence must end with one or more citations such as [1].
If the evidence directly states the requested process, number, actor, or deadline, report it rather than claiming it is unspecified.
Answer every part of a multi-part question; do not omit extension, renewal, distribution, or approval conditions that were asked.
Apply the configured hierarchy only across different documents: IEEE Constitution & Bylaws (100),
SMCS Constitution & Bylaws (90), Corrected Operations Manual (80), SMCS Technical Manual (70).
For a cross-document conflict, retain both passages and explain that the higher authority governs.
For a within-document conflict, do not choose a winner. Identify conflicting normative terms,
present both reasonable interpretations, state that hierarchy cannot resolve equal-authority clauses,
recommend authorised human review, and abstain from a definitive rule.
Do not invent a conflict-resolution provision, governance rule, or legal interpretation.
Detected conflict scope from deterministic validation: {conflict_scope or 'none'}.
Return strict JSON only: {{"answer":"...", "citation_indices":[1]}}.

QUESTION:
{question}

EVIDENCE (approved production documents only):
{evidence}
"""
        if self.provider == "ollama":
            response = httpx.post(f"{Config.OLLAMA_BASE_URL}/api/generate", json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
            }, timeout=180.0)
            response.raise_for_status()
            output_text = response.json().get("response", "")
        elif self.provider == "openai":
            response = self._client.responses.create(model=self.model, input=prompt, temperature=0)
            output_text = response.output_text
        else:
            raise RuntimeError(f"Unsupported LLM provider: {self.provider}")
        payload = json.loads(output_text)
        answer = str(payload.get("answer", "")).strip()
        indices = sorted({int(value) for value in payload.get("citation_indices", [])})
        if not answer or not indices or any(index < 1 or index > len(citations) for index in indices):
            raise ValueError("LLM returned an unsupported or invalid citation set.")
        markers = {int(value) for value in re.findall(r"\[(\d+)\]", answer)}
        if not markers:
            unsupported = re.search(
                r"\b(?:not specified|cannot find|insufficient evidence|not provided|unknown)\b",
                answer, re.I)
            cited_evidence = " ".join(citations[index - 1].evidence_text for index in indices)
            answer_terms = set(re.findall(r"[a-z0-9]+", answer.lower())) - {
                "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
                "is", "of", "on", "or", "the", "to", "with",
            }
            evidence_terms = set(re.findall(r"[a-z0-9]+", cited_evidence.lower()))
            support = len(answer_terms & evidence_terms) / max(1, len(answer_terms))
            if unsupported or support < 0.45:
                raise ValueError("LLM answer contains no inline citation marker and is not sufficiently extractive.")
            answer = f"{answer} {' '.join(f'[{index}]' for index in indices)}"
            markers = set(indices)
        if markers != set(indices):
            raise ValueError("LLM citation markers do not match its declared citation set.")
        if (re.search(r"\b(?:extend|extended|extension|renew|renewed|renewal)\b", question, re.I) and
                not re.search(r"\b(?:extend|extended|extension|renew|renewed|renewal)\b", answer, re.I)):
            raise ValueError("LLM answer omitted the requested extension or renewal condition.")
        return answer, indices
