export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
export type RAGMode = "deterministic" | "bm25" | "dense" | "rrf" | "hybrid" | "hybrid_llm";

export type Citation = { document_id: string; document_title: string; section: string | null; page: number | null; evidence_text: string; authority_score: number | null; approval_status: string | null; version: string | null };
export type ConflictDetails = { conflict_status: "none" | "possible" | "confirmed" | "ambiguous_internal_conflict"; conflict_scope: "cross_document" | "within_document" | null; higher_authority_evidence: Citation | null; conflicting_evidence: Citation[]; authority_scores: Record<string, number>; conflicting_normative_terms: string[]; interpretations: string[]; resolution_basis: string | null; human_review_required: boolean };
export type ChatResult = ConflictDetails & { answer: string; citations: Citation[]; conflicts: { applied_rule: string }[]; confidence: number; abstained: boolean; abstention_reason: string | null; mode: RAGMode; requested_mode: RAGMode; fallback_reason: string | null; latency_ms: number };
export type DocumentRecord = { document_id: string; title: string; version: string; document_type: string; approval_status: string; authority_level: number; usage: string; retrieval_enabled: boolean };
export type AuditResult = ConflictDetails & { issue_type: string | null; issue_subtype: string | null; audited_text: string; authoritative_evidence: Citation[]; explanation: string; citation: Citation | null; suggested_correction: string | null; confidence: number; abstention_reason: string | null };
export type EvaluationResult = {
  scored_cases: number; positive_cases: number; negative_cases: number;
  true_positives: number; false_negatives: number; true_negatives: number; false_positives: number;
  detection_recall: number | null; false_positive_rate: number | null; issue_type_accuracy: number;
  citation_accuracy: number; correction_accuracy: number; abstentions: number;
  metric_formulas: Record<string, string>; limitation: string | null;
  per_case: { gold_id: string; expected_issue: string; expected_subtype: string; predicted_issue: string | null; predicted_subtype: string | null; outcome: string; detected: boolean; abstained: boolean; failure_category: string | null; retrieval_result: string | null; retrieval_score: number | null }[];
  mode: RAGMode; retrieval_recall_at_k: number; retrieval_evaluable_cases: number;
  mean_reciprocal_rank: number; ndcg_at_10: number; average_latency_ms: number;
};
export type ComparisonResult = { development_benchmark: boolean; embedding_configuration: Record<string, string>; llm_configuration: Record<string, string | boolean>; modes: EvaluationResult[] };
export type HealthResult = { status: string; default_mode: RAGMode; development_mode: boolean; embedding: Record<string, string> };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : Array.isArray(body.detail) ? body.detail.map((item: { msg?: string }) => item.msg || "Invalid request").join("; ") : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return response.json();
}

export const api = {
  chat: (question: string, mode: RAGMode = "deterministic") => request<ChatResult>("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, mode }) }),
  audit: (text: string, document_id?: string, mode: RAGMode = "deterministic") => request<AuditResult>("/api/audit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, document_id: document_id || null, mode }) }),
  documents: () => request<DocumentRecord[]>("/api/documents"),
  evaluation: () => request<EvaluationResult>("/api/evaluation/run", { method: "POST" }),
  comparison: () => request<ComparisonResult>("/api/evaluation/compare", { method: "POST" }),
  health: () => request<HealthResult>("/api/health"),
};
