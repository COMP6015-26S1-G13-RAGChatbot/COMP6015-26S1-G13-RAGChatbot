from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


Usage = Literal["production", "audit_input", "evaluation_only", "pending"]
ConflictStatus = Literal["none", "possible", "confirmed"]


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


class Conflict(BaseModel):
    topic: str
    lower_authority_document: str
    higher_authority_document: str
    lower_authority_evidence: str
    higher_authority_evidence: str
    applied_rule: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    conflict_status: ConflictStatus
    conflicts: list[Conflict]
    confidence: float = Field(ge=0, le=1)
    abstained: bool
    abstention_reason: str | None = None
    mode: Literal["deterministic_offline"] = "deterministic_offline"


class AuditRequest(BaseModel):
    text: str | None = Field(default=None, max_length=10000)
    document_id: str | None = None


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


class RetrievalDebugRequest(BaseModel):
    query: str = Field(min_length=2, max_length=10000)
    document_ids: list[str] | None = None


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
    reranking_score: float
    included: bool
    reason: str


class RetrievalDebugResponse(BaseModel):
    query: str
    candidates: list[RetrievalDebugCandidate]
