export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Citation = { document_id: string; document_title: string; section: string | null; page: number | null; evidence_text: string };
export type ChatResult = { answer: string; citations: Citation[]; conflict_status: "none" | "possible" | "confirmed"; conflicts: { applied_rule: string }[]; confidence: number; abstained: boolean; abstention_reason: string | null; mode: string };
export type DocumentRecord = { document_id: string; title: string; version: string; document_type: string; approval_status: string; authority_level: number; usage: string; retrieval_enabled: boolean };
export type AuditResult = { conflict_status: string; issue_type: string | null; issue_subtype: string | null; audited_text: string; authoritative_evidence: Citation[]; explanation: string; citation: Citation | null; suggested_correction: string | null; confidence: number; abstention_reason: string | null };
export type EvaluationResult = {
  scored_cases: number; positive_cases: number; negative_cases: number;
  true_positives: number; false_negatives: number; true_negatives: number; false_positives: number;
  detection_recall: number | null; false_positive_rate: number | null; issue_type_accuracy: number;
  citation_accuracy: number; correction_accuracy: number; abstentions: number;
  metric_formulas: Record<string, string>; limitation: string | null;
  per_case: { gold_id: string; expected_issue: string; expected_subtype: string; predicted_issue: string | null; predicted_subtype: string | null; outcome: string; detected: boolean; abstained: boolean; failure_category: string | null; retrieval_result: string | null; retrieval_score: number | null }[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${response.status})`);
  }
  return response.json();
}

export const api = {
  chat: (question: string) => request<ChatResult>("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) }),
  audit: (text: string, document_id?: string) => request<AuditResult>("/api/audit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, document_id: document_id || null }) }),
  documents: () => request<DocumentRecord[]>("/api/documents"),
  evaluation: () => request<EvaluationResult>("/api/evaluation/run", { method: "POST" }),
};
