"use client";

import { useEffect, useState } from "react";
import { api, AuditResult, ChatResult, DocumentRecord, EvaluationResult } from "@/lib/api";

type View = "Chat" | "Policy Audit" | "Documents" | "Evaluation";

function Citations({ items }: { items: ChatResult["citations"] }) {
  return <div className="citations">{items.map((item, index) => <details key={`${item.document_id}-${item.page}-${index}`}>
    <summary>[{index + 1}] {item.document_title} · {item.section || "section unavailable"}{item.page ? ` · p. ${item.page}` : ""}</summary>
    <blockquote>{item.evidence_text}</blockquote>
  </details>)}</div>;
}

function Status({ kind, children }: { kind: string; children: React.ReactNode }) {
  return <div className={`status ${kind}`}>{children}</div>;
}

export default function App() {
  const [view, setView] = useState<View>("Chat");
  const [question, setQuestion] = useState("");
  const [chat, setChat] = useState<ChatResult | null>(null);
  const [auditText, setAuditText] = useState("");
  const [auditDocument, setAuditDocument] = useState("");
  const [audit, setAudit] = useState<AuditResult | null>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [evaluation, setEvaluation] = useState<EvaluationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.documents().then(setDocuments).catch(() => undefined); }, []);
  const run = async (action: () => Promise<void>) => { setLoading(true); setError(null); try { await action(); } catch (err) { setError(err instanceof Error ? err.message : "Unknown error"); } finally { setLoading(false); } };

  return <div className="app-shell">
    <header><div className="brand"><span className="mark">IEEE<br/>SMC</span><div><strong>Authority-aware Policy Assistant</strong><small>Approved evidence · cite or abstain</small></div></div><span className="mode">Deterministic offline mode</span></header>
    <nav>{(["Chat", "Policy Audit", "Documents", "Evaluation"] as View[]).map(item => <button className={view === item ? "active" : ""} key={item} onClick={() => { setView(item); setError(null); }}>{item}</button>)}</nav>
    <main>
      {error && <Status kind="error">{error}</Status>}
      {view === "Chat" && <section><div className="eyebrow">Primary product</div><h1>Ask the approved SMCS corpus</h1><p className="lede">Answers use production documents only. The Corrected Operations Manual wins configured authority conflicts.</p>
        <form onSubmit={event => { event.preventDefault(); run(async () => setChat(await api.chat(question))); }}><textarea aria-label="Chat question" value={question} onChange={e => setQuestion(e.target.value)} placeholder="What is the process for a Vice-President vacancy?" required/><button disabled={loading}>{loading ? "Retrieving…" : "Ask question"}</button></form>
        {chat && <article className="result">{chat.abstained ? <Status kind="insufficient"><strong>Insufficient evidence.</strong> {chat.abstention_reason}</Status> : <><div className="result-head"><span className="pill">Confidence {Math.round(chat.confidence * 100)}%</span><span className="pill">{chat.mode.replaceAll("_", " ")}</span></div><p>{chat.answer}</p></>}{chat.conflict_status !== "none" && <Status kind="warning"><strong>{chat.conflict_status} conflict.</strong> {chat.conflicts.map(c => c.applied_rule).join(" ")}</Status>}<Citations items={chat.citations}/></article>}
      </section>}
      {view === "Policy Audit" && <section><div className="eyebrow">Separate workflow</div><h1>Policy Audit</h1><p className="lede">Check a non-authoritative clause against retrieved Corrected Operations Manual evidence.</p>
        <form onSubmit={event => { event.preventDefault(); run(async () => setAudit(await api.audit(auditText, auditDocument))); }}><select aria-label="Audit document" value={auditDocument} onChange={e => setAuditDocument(e.target.value)}><option value="">Pasted clause (no registered document)</option>{documents.filter(d => ["audit_input", "pending"].includes(d.usage)).map(d => <option key={d.document_id} value={d.document_id}>{d.title}</option>)}</select><textarea aria-label="Clause to audit" value={auditText} onChange={e => setAuditText(e.target.value)} placeholder="Paste or select a clause to audit…" required/><button disabled={loading}>{loading ? "Retrieving authority…" : "Run audit"}</button></form>
        {audit && <article className="result"><Status kind={audit.abstention_reason ? "insufficient" : audit.conflict_status === "none" ? "success" : "warning"}><strong>{audit.abstention_reason ? "Insufficient evidence" : audit.conflict_status === "none" ? "No conflict detected" : `${audit.conflict_status} conflict`}</strong>{audit.abstention_reason ? ` ${audit.abstention_reason}` : ""}</Status><dl><dt>Issue type</dt><dd>{audit.issue_type || "—"}</dd><dt>Subtype</dt><dd>{audit.issue_subtype || "—"}</dd><dt>Explanation</dt><dd>{audit.explanation}</dd><dt>Suggested correction</dt><dd>{audit.suggested_correction || "No correction suggested."}</dd></dl><Citations items={audit.authoritative_evidence}/></article>}
      </section>}
      {view === "Documents" && <section><div className="eyebrow">Registry</div><h1>Documents</h1><p className="lede">Searchability requires approved status, production usage, and retrieval enabled.</p><div className="document-grid">{documents.map(doc => <article className="document" key={doc.document_id}><div className="result-head"><span className={`dot ${doc.retrieval_enabled ? "on" : ""}`}/><span>{doc.retrieval_enabled ? "Searchable" : "Excluded"}</span></div><h2>{doc.title}</h2><p>{doc.version} · {doc.document_type.replaceAll("_", " ")}</p><dl><dt>Approval</dt><dd>{doc.approval_status}</dd><dt>Authority</dt><dd>{doc.authority_level}</dd><dt>Usage</dt><dd>{doc.usage}</dd></dl>{!doc.retrieval_enabled && <small>Excluded because it is {doc.usage.replaceAll("_", " ")} / {doc.approval_status}.</small>}</article>)}</div></section>}
      {view === "Evaluation" && <section><div className="eyebrow">Evaluation only</div><h1>Golden Set Evaluation</h1><p className="lede">Ground-truth columns are isolated from prediction. Metrics are calculated only after predictions complete.</p><button onClick={() => run(async () => setEvaluation(await api.evaluation()))} disabled={loading}>{loading ? "Evaluating…" : "Run evaluation"}</button>{evaluation && <><div className="metrics">{[
        ["Total scored", evaluation.scored_cases, false], ["Positive", evaluation.positive_cases, false], ["Negative / no issue", evaluation.negative_cases, false],
        ["True positives", evaluation.true_positives, false], ["False negatives", evaluation.false_negatives, false], ["True negatives", evaluation.true_negatives, false], ["False positives", evaluation.false_positives, false],
        ["Detection recall", evaluation.detection_recall, true], ["False-positive rate", evaluation.false_positive_rate, true], ["Issue-type accuracy", evaluation.issue_type_accuracy, true], ["Citation accuracy", evaluation.citation_accuracy, true], ["Correction accuracy", evaluation.correction_accuracy, true],
      ].map(([label, value, percentage]) => <div key={String(label)}><small>{label}</small><strong>{typeof value === "number" && percentage ? `${Math.round(value * 100)}%` : value ?? "N/A"}</strong></div>)}</div>
      <div className="formulas"><h2>Metric formulas</h2>{Object.entries(evaluation.metric_formulas).map(([metric, formula]) => <p key={metric}><strong>{metric.replaceAll("_", " ")}:</strong> {formula}</p>)}</div>
      {evaluation.limitation && <Status kind="warning">{evaluation.limitation}</Status>}<div className="case-table"><div className="case-header"><strong>Case</strong><strong>Expected</strong><strong>Predicted</strong><strong>Outcome</strong><strong>Failure</strong></div>{evaluation.per_case.map(item => <div key={item.gold_id}><strong>{item.gold_id}</strong><span>{item.expected_issue}</span><span>{item.predicted_issue || "Abstained"}</span><span>{item.outcome.replaceAll("_", " ")}</span><small>{item.failure_category || "—"}</small></div>)}</div></>}</section>}
    </main><footer>Official documents remain the source of truth · Evaluation content is never searchable</footer>
  </div>;
}
