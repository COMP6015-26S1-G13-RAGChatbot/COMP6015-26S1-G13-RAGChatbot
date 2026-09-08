from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


Usage = Literal["production", "audit_input", "evaluation_only", "pending"]
ConflictStatus = Literal["none", "possible", "confirmed", "ambiguous_internal_conflict"]
ConflictScope = Literal["cross_document", "within_document"]
RAGMode = Literal["deterministic", "bm25", "dense", "rrf", "hybrid", "hybrid_llm"]


class DocumentRecord(BaseModel):
    document_id: str
    title: str
    version: str
    document_type: str
    approval_status: str
    authority_level: int
    effective_date: date | None = None
    content_hash: str
    source_path: str
    retrieval_enabled: bool
    usage: Usage


class Citation(BaseModel):
    document_id: str
    document_title: str
    section: str | None = None
    page: int | None = None
    evidence_text: str
    authority_score: int | None = None
    approval_status: str | None = None
    version: str | None = None


class Conflict(BaseModel):
    topic: str
    lower_authority_document: str | None = None
    higher_authority_document: str | None = None
    lower_authority_evidence: Citation | None = None
    higher_authority_evidence: Citation | None = None
    applied_rule: str
    conflict_scope: ConflictScope = "cross_document"
    conflicting_evidence: list[Citation] = Field(default_factory=list)
    authority_scores: dict[str, int] = Field(default_factory=dict)
    conflicting_normative_terms: list[str] = Field(default_factory=list)
    interpretations: list[str] = Field(default_factory=list)
    resolution_basis: str
    human_review_required: bool = False


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    mode: RAGMode = "deterministic"


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    conflict_status: ConflictStatus
    conflicts: list[Conflict]
    confidence: float = Field(ge=0, le=1)
    abstained: bool
    abstention_reason: str | None = None
    mode: RAGMode = "deterministic"
    requested_mode: RAGMode = "deterministic"
    fallback_reason: str | None = None
    latency_ms: float = 0
    conflict_scope: ConflictScope | None = None
    higher_authority_evidence: Citation | None = None
    conflicting_evidence: list[Citation] = Field(default_factory=list)
    authority_scores: dict[str, int] = Field(default_factory=dict)
    conflicting_normative_terms: list[str] = Field(default_factory=list)
    interpretations: list[str] = Field(default_factory=list)
    resolution_basis: str | None = None
    human_review_required: bool = False


class AuditRequest(BaseModel):
    text: str | None = Field(default=None, max_length=10000)
    document_id: str | None = None
    mode: RAGMode = "deterministic"


class AuditResponse(BaseModel):
    conflict_status: ConflictStatus
    issue_type: str | None
    issue_subtype: str | None = None
    audited_text: str
    authoritative_evidence: list[Citation]
    explanation: str
    citation: Citation | None
    suggested_correction: str | None
    confidence: float = Field(ge=0, le=1)
    abstention_reason: str | None
    conflict_scope: ConflictScope | None = None
    higher_authority_evidence: Citation | None = None
    conflicting_evidence: list[Citation] = Field(default_factory=list)
    authority_scores: dict[str, int] = Field(default_factory=dict)
    conflicting_normative_terms: list[str] = Field(default_factory=list)
    interpretations: list[str] = Field(default_factory=list)
    resolution_basis: str | None = None
    human_review_required: bool = False


class EvaluationCase(BaseModel):
    gold_id: str
    expected_issue: str
    expected_subtype: str
    predicted_issue: str | None
    predicted_subtype: str | None
    expected_positive: bool
    predicted_positive: bool
    outcome: Literal["true_positive", "false_negative", "true_negative", "false_positive"]
    detected: bool
    issue_type_correct: bool
    citation_correct: bool
    correction_correct: bool
    abstained: bool
    retrieval_result: str | None
    retrieval_score: float | None
    failure_category: str | None
    latency_ms: float = 0
    retrieval_hit: bool = False
    retrieval_rank: int | None = None
    reciprocal_rank: float = 0
    ndcg_at_10: float = 0


class EvaluationResponse(BaseModel):
    scored_cases: int
    positive_cases: int
    negative_cases: int
    true_positives: int
    false_negatives: int
    true_negatives: int
    detection_recall: float | None
    false_positives: int
    false_positive_rate: float | None
    issue_type_accuracy: float
    citation_accuracy: float
    correction_accuracy: float
    abstentions: int
    metric_formulas: dict[str, str]
    limitation: str | None
    per_case: list[EvaluationCase]
    mode: RAGMode = "deterministic"
    retrieval_recall_at_k: float = 0
    mean_reciprocal_rank: float = 0
    ndcg_at_10: float = 0
    retrieval_evaluable_cases: int = 0
    average_latency_ms: float = 0


class ComparisonResponse(BaseModel):
    development_benchmark: bool = True
    embedding_configuration: dict[str, str]
    llm_configuration: dict[str, str | bool]
    modes: list[EvaluationResponse]


class RetrievalDebugRequest(BaseModel):
    query: str = Field(min_length=2, max_length=10000)
    document_ids: list[str] | None = None
    mode: RAGMode = "hybrid"


class RetrievalDebugCandidate(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    section: str | None
    page: int
    authority_level: int
    approval_status: str
    usage: str
    candidate_clause: str
    lexical_score: float
    vector_score: float = 0
    hybrid_score: float = 0
    reranking_score: float
    bm25_score: float = 0
    rrf_score: float = 0
    included: bool
    reason: str


class RetrievalDebugResponse(BaseModel):
    query: str
    candidates: list[RetrievalDebugCandidate]
