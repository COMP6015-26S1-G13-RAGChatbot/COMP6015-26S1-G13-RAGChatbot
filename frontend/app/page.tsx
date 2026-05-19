"use client";

import { useState, useRef, useEffect } from "react";

const parseSource = (src: string) => {
  const typeMatch = src.match(/^\[([^\]]+)\]/);
  const fileMatch = src.match(/\]\s+(.+?)\s*\(Page:/);
  const pageMatch = src.match(/\(Page:\s*(\d+)\)/);
  const snippetMatch = src.match(/Snippet:\s*"(.+)"$/);
  return {
    type: typeMatch ? typeMatch[1] : "UNKNOWN",
    filename: fileMatch ? fileMatch[1] : src,
    page: pageMatch ? pageMatch[1] : "?",
    snippet: snippetMatch ? snippetMatch[1].replace(/\\n/g, " ").trim() : "",
  };
};

const typeConfig: Record<string, { bg: string; text: string; border: string; accent: string; label: string; icon: string }> = {
  LEGAL: {
    bg: "#F0F4FF",
    text: "#1E3A6E",
    border: "#C7D7F5",
    accent: "#2B52A8",
    label: "Legal",
    icon: "⚖",
  },
  OPERATIONAL: {
    bg: "#F0FAF4",
    text: "#1A4731",
    border: "#B8E3C8",
    accent: "#1E7A45",
    label: "Operational",
    icon: "◈",
  },
  UNKNOWN: {
    bg: "#F7F7F7",
    text: "#444",
    border: "#DDD",
    accent: "#666",
    label: "Document",
    icon: "▪",
  },
};

function renderMarkdown(text: string) {
  if (!text) return null;
  const lines = text.split("\n");
  const elements: React.ReactNode[] = [];
  let key = 0;

  for (const line of lines) {
    if (!line.trim()) {
      elements.push(<div key={key++} style={{ height: 8 }} />);
      continue;
    }
    // Bold heading: **Text**
    if (/^\*\*[^*]+\*\*$/.test(line.trim())) {
      elements.push(
        <p key={key++} style={{ fontWeight: 700, fontSize: 13, margin: "14px 0 4px", color: "#1a2744", letterSpacing: "0.01em", textTransform: "uppercase", borderBottom: "1px solid #E5EAF5", paddingBottom: 4 }}>
          {line.trim().slice(2, -2)}
        </p>
      );
      continue;
    }
    const html = line.replace(/\*\*(.+?)\*\*/g, (_, t) => `<strong>${t}</strong>`);
    elements.push(
      <p key={key++} style={{ margin: "5px 0", lineHeight: 1.75, fontSize: 14, color: "#2C3A50" }}
        dangerouslySetInnerHTML={{ __html: html }} />
    );
  }
  return <>{elements}</>;
}

function SourceCard({ source, pdfBaseUrl }: { source: string; pdfBaseUrl: string }) {
  const [expanded, setExpanded] = useState(false);
  const parsed = parseSource(source);
  const cfg = typeConfig[parsed.type] || typeConfig.UNKNOWN;

  const subFolder = parsed.type === "LEGAL" ? "legal" : parsed.type === "OPERATIONAL" ? "operational" : "";
  const pdfUrl = pdfBaseUrl && subFolder
    ? `${pdfBaseUrl.replace(/\/$/, "")}/${subFolder}/${encodeURIComponent(parsed.filename)}#page=${parsed.page}`
    : null;

  return (
    <div style={{ border: `1px solid ${cfg.border}`, borderRadius: 8, background: cfg.bg, marginBottom: 6, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "stretch" }}>
        {/* Left accent bar */}
        <div style={{ width: 3, background: cfg.accent, flexShrink: 0 }} />
        <button
          onClick={() => setExpanded(!expanded)}
          style={{
            flex: 1, display: "flex", alignItems: "center", gap: 10,
            padding: "9px 12px", background: "transparent", border: "none",
            cursor: "pointer", textAlign: "left", minWidth: 0,
          }}
        >
          <span style={{
            fontSize: 10, fontWeight: 700, letterSpacing: "0.08em",
            color: cfg.accent, background: `${cfg.accent}18`,
            borderRadius: 4, padding: "2px 7px", flexShrink: 0, textTransform: "uppercase",
          }}>
            {cfg.icon} {cfg.label}
          </span>
          <span style={{ fontSize: 13, color: cfg.text, fontWeight: 500, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {parsed.filename}
          </span>
          <span style={{ fontSize: 11, color: cfg.accent, fontWeight: 600, flexShrink: 0, background: `${cfg.accent}12`, padding: "2px 7px", borderRadius: 4 }}>
            p. {parsed.page}
          </span>
          <span style={{ fontSize: 10, color: cfg.text, opacity: 0.5, flexShrink: 0, marginLeft: 4 }}>
            {expanded ? "▲" : "▼"}
          </span>
        </button>
        {pdfUrl && (
          <a
            href={pdfUrl} target="_blank" rel="noopener noreferrer"
            style={{
              display: "flex", alignItems: "center", gap: 5,
              padding: "0 14px", background: cfg.accent, color: "#fff",
              fontSize: 11, fontWeight: 600, textDecoration: "none",
              flexShrink: 0, letterSpacing: "0.03em", transition: "opacity 0.15s",
            }}
            onMouseEnter={e => (e.currentTarget.style.opacity = "0.85")}
            onMouseLeave={e => (e.currentTarget.style.opacity = "1")}
          >
            ↗ View
          </a>
        )}
      </div>
      {expanded && parsed.snippet && (
        <div style={{
          padding: "10px 15px 12px 15px",
          borderTop: `1px solid ${cfg.border}`,
          fontSize: 12.5,
          color: cfg.text,
          lineHeight: 1.7,
          fontStyle: "italic",
          background: `${cfg.accent}08`,
        }}>
          <span style={{ opacity: 0.5, marginRight: 4 }}>"</span>
          {parsed.snippet}
          <span style={{ opacity: 0.5, marginLeft: 4 }}>"</span>
        </div>
      )}
    </div>
  );
}

function Message({ msg, pdfBaseUrl }: { msg: any; pdfBaseUrl: string }) {
  const isUser = msg.role === "user";

  if (isUser) {
    return (
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 20 }}>
        <div style={{ maxWidth: "72%" }}>
          <div style={{
            background: "#1E3A6E",
            borderRadius: "12px 2px 12px 12px",
            padding: "12px 18px",
            fontSize: 14,
            color: "#fff",
            lineHeight: 1.7,
            boxShadow: "0 2px 8px rgba(30,58,110,0.15)",
          }}>
            {msg.content}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", gap: 14, marginBottom: 24, maxWidth: "100%" }}>
      {/* AI Avatar */}
      <div style={{ flexShrink: 0, paddingTop: 2 }}>
        <div style={{
          width: 34, height: 34, borderRadius: 8,
          background: "linear-gradient(135deg, #1E3A6E 0%, #2B52A8 100%)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 12, color: "#fff", fontWeight: 800, letterSpacing: "0.02em",
          boxShadow: "0 2px 6px rgba(30,58,110,0.2)",
        }}>
          SMC
        </div>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          background: "#fff",
          border: "1px solid #E5EAF5",
          borderRadius: "2px 12px 12px 12px",
          padding: "16px 20px",
          boxShadow: "0 2px 8px rgba(0,0,0,0.04)",
        }}>
          {renderMarkdown(msg.content)}
        </div>
        {msg.sources && msg.sources.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div style={{
              display: "flex", alignItems: "center", gap: 8, marginBottom: 8,
            }}>
              <div style={{ height: 1, flex: 1, background: "#E5EAF5" }} />
              <span style={{ fontSize: 11, color: "#8A96AA", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                {msg.sources.length} Source{msg.sources.length > 1 ? "s" : ""} Referenced
              </span>
              <div style={{ height: 1, flex: 1, background: "#E5EAF5" }} />
            </div>
            {msg.sources.map((src: string, i: number) => (
              <SourceCard key={i} source={src} pdfBaseUrl={pdfBaseUrl} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [messages, setMessages] = useState<any[]>([
    {
      role: "assistant",
      content: "Welcome. I am the IEEE SMC Society Policy Assistant.\n\nI can answer questions about Society bylaws, operational policies, chapter resources, conference procedures, publications, and governance matters.\n\n**Important:** Every answer I provide is grounded in official IEEE SMC documents. I will cite my sources for every claim, and I will abstain from answering if the corpus does not contain sufficient information.",
      sources: [],
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [apiUrl, setApiUrl] = useState("http://localhost:8000/ask");
  const [pdfBaseUrl, setPdfBaseUrl] = useState("http://localhost:8000/documents");
  const [showSettings, setShowSettings] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleSend = async () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput("");
    setMessages(prev => [...prev, { role: "user", content: q }]);
    setLoading(true);
    try {
      const res = await fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      const data = await res.json();
      setMessages(prev => [...prev, {
        role: "assistant",
        content: data.answer || "No answer returned.",
        sources: data.sources || [],
      }]);
    } catch (err: any) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `**Connection Error**\n\n${err.message}\n\nPlease verify the backend is running and the API endpoint in Settings is correct.`,
        sources: [],
      }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const SUGGESTED = [
    "What are the duties of the SMC Society President?",
    "How are chapter elections conducted?",
    "What is the publication policy for SMCS?",
    "What travel grants are available for volunteers?",
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "#F4F6FB", fontFamily: "'Georgia', 'Times New Roman', serif" }}>

      {/* Top navigation bar */}
      <div style={{ background: "#0D1F3C", height: 4, flexShrink: 0 }} />
      <div style={{
        background: "#fff",
        borderBottom: "1px solid #DDE3EE",
        padding: "0 28px",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        height: 64, flexShrink: 0,
        boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          {/* IEEE-style logo block */}
          <div style={{
            display: "flex", alignItems: "center", gap: 0,
            borderRight: "1px solid #DDE3EE", paddingRight: 16,
          }}>
            <div style={{
              width: 42, height: 42, borderRadius: 6,
              background: "linear-gradient(135deg, #0D1F3C 0%, #1E3A6E 60%, #2B52A8 100%)",
              display: "flex", alignItems: "center", justifyContent: "center",
              color: "#fff", fontSize: 11, fontWeight: 900, letterSpacing: "0.05em",
              fontFamily: "sans-serif", lineHeight: 1.2, textAlign: "center",
            }}>
              <span>IEEE<br/>SMC</span>
            </div>
          </div>
          <div style={{ paddingLeft: 4 }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: "#0D1F3C", letterSpacing: "-0.01em", fontFamily: "sans-serif" }}>
              Policy Assistant
            </div>
            <div style={{ fontSize: 11, color: "#7A8599", letterSpacing: "0.04em", fontFamily: "sans-serif", marginTop: 1 }}>
              Systems, Man &amp; Cybernetics Society · RAG Chatbot
            </div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {/* Corpus indicators */}
          <div style={{ display: "flex", gap: 6, marginRight: 8 }}>
            <span style={{ fontSize: 11, background: "#F0F4FF", color: "#1E3A6E", border: "1px solid #C7D7F5", borderRadius: 4, padding: "3px 9px", fontFamily: "sans-serif", fontWeight: 600 }}>
              ⚖ Legal
            </span>
            <span style={{ fontSize: 11, background: "#F0FAF4", color: "#1A4731", border: "1px solid #B8E3C8", borderRadius: 4, padding: "3px 9px", fontFamily: "sans-serif", fontWeight: 600 }}>
              ◈ Operational
            </span>
          </div>
          <button
            onClick={() => setShowSettings(!showSettings)}
            style={{
              background: showSettings ? "#F0F4FF" : "transparent",
              border: "1px solid #DDE3EE",
              borderRadius: 6, padding: "6px 14px",
              color: "#4A5568", fontSize: 12, cursor: "pointer",
              fontFamily: "sans-serif", fontWeight: 500,
              display: "flex", alignItems: "center", gap: 6,
            }}
          >
            ⚙ Settings
          </button>
        </div>
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div style={{
          background: "#F9FAFC", borderBottom: "1px solid #DDE3EE",
          padding: "16px 28px", flexShrink: 0,
        }}>
          <div style={{ maxWidth: 700, display: "flex", flexDirection: "column", gap: 10 }}>
            <p style={{ margin: "0 0 6px", fontSize: 11, fontWeight: 700, color: "#4A5568", textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "sans-serif" }}>
              Connection Settings
            </p>
            {[
              { label: "API Endpoint", value: apiUrl, setter: setApiUrl, placeholder: "http://localhost:8000/ask" },
              { label: "PDF Base URL", value: pdfBaseUrl, setter: setPdfBaseUrl, placeholder: "http://localhost:8000/documents" },
            ].map(({ label, value, setter, placeholder }) => (
              <div key={label} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <label style={{ fontSize: 12, color: "#4A5568", width: 110, flexShrink: 0, fontFamily: "sans-serif", fontWeight: 500 }}>{label}</label>
                <input
                  value={value}
                  onChange={e => setter(e.target.value)}
                  placeholder={placeholder}
                  style={{
                    flex: 1, fontSize: 12, padding: "7px 11px", borderRadius: 5,
                    border: "1px solid #C8D0E0", background: "#fff",
                    color: "#1E3A6E", fontFamily: "monospace", outline: "none",
                  }}
                />
              </div>
            ))}
            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 4 }}>
              <button
                onClick={() => setShowSettings(false)}
                style={{
                  background: "#1E3A6E", border: "none", borderRadius: 5,
                  padding: "7px 18px", color: "#fff", fontSize: 12, cursor: "pointer",
                  fontFamily: "sans-serif", fontWeight: 600,
                }}
              >
                Save &amp; Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main content area */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", maxWidth: 900, width: "100%", margin: "0 auto", padding: "0 20px" }}>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: "auto", paddingTop: 28, paddingBottom: 8 }}>
          {messages.map((msg, i) => (
            <Message key={i} msg={msg} pdfBaseUrl={pdfBaseUrl} />
          ))}

          {/* Loading */}
          {loading && (
            <div style={{ display: "flex", gap: 14, marginBottom: 24 }}>
              <div style={{
                width: 34, height: 34, borderRadius: 8, flexShrink: 0,
                background: "linear-gradient(135deg, #1E3A6E, #2B52A8)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 12, color: "#fff", fontWeight: 800, fontFamily: "sans-serif",
              }}>SMC</div>
              <div style={{
                background: "#fff", border: "1px solid #E5EAF5",
                borderRadius: "2px 12px 12px 12px",
                padding: "16px 20px", display: "flex", gap: 6, alignItems: "center",
                boxShadow: "0 2px 8px rgba(0,0,0,0.04)",
              }}>
                <span style={{ fontSize: 12, color: "#8A96AA", fontFamily: "sans-serif", marginRight: 8 }}>Retrieving sources</span>
                {[0, 1, 2].map(i => (
                  <span key={i} style={{
                    width: 7, height: 7, borderRadius: "50%", background: "#2B52A8",
                    display: "inline-block", animation: "pulse 1.2s infinite",
                    animationDelay: `${i * 0.2}s`,
                  }} />
                ))}
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Suggested questions — shown only at start */}
        {messages.length === 1 && (
          <div style={{ paddingBottom: 16 }}>
            <p style={{ fontSize: 11, color: "#8A96AA", fontFamily: "sans-serif", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 8 }}>
              Suggested Questions
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {SUGGESTED.map(q => (
                <button
                  key={q}
                  onClick={() => { setInput(q); textareaRef.current?.focus(); }}
                  style={{
                    background: "#fff", border: "1px solid #DDE3EE", borderRadius: 8,
                    padding: "10px 14px", cursor: "pointer", textAlign: "left",
                    fontSize: 13, color: "#2C3A50", lineHeight: 1.4,
                    fontFamily: "Georgia, serif", transition: "border-color 0.15s, box-shadow 0.15s",
                  }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = "#2B52A8"; e.currentTarget.style.boxShadow = "0 2px 8px rgba(43,82,168,0.1)"; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = "#DDE3EE"; e.currentTarget.style.boxShadow = "none"; }}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Input area */}
        <div style={{
          background: "#fff", border: "1px solid #DDE3EE",
          borderRadius: 10, marginBottom: 16,
          boxShadow: "0 2px 12px rgba(0,0,0,0.06)",
          overflow: "hidden",
        }}>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about IEEE SMC policies, bylaws, chapter operations, or governance..."
            rows={2}
            style={{
              width: "100%", border: "none", outline: "none",
              resize: "none", padding: "14px 16px",
              fontSize: 14, color: "#2C3A50", lineHeight: 1.7,
              fontFamily: "Georgia, serif", background: "transparent",
              boxSizing: "border-box",
            }}
          />
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "8px 12px 10px",
            borderTop: "1px solid #F0F2F8",
          }}>
            <span style={{ fontSize: 11, color: "#B0B8C8", fontFamily: "sans-serif" }}>
              Press Enter to send · Shift+Enter for new line
            </span>
            <button
              onClick={handleSend}
              disabled={!input.trim() || loading}
              style={{
                background: input.trim() && !loading ? "#1E3A6E" : "#C8D0E0",
                border: "none", borderRadius: 6, padding: "8px 20px",
                color: "#fff", fontSize: 13, cursor: input.trim() && !loading ? "pointer" : "default",
                fontFamily: "sans-serif", fontWeight: 600, letterSpacing: "0.02em",
                transition: "background 0.15s", display: "flex", alignItems: "center", gap: 6,
              }}
            >
              Submit ↑
            </button>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div style={{
        background: "#fff", borderTop: "1px solid #DDE3EE",
        padding: "8px 28px", flexShrink: 0,
        display: "flex", justifyContent: "center",
      }}>
        <p style={{ fontSize: 11, color: "#A0A8B8", fontFamily: "sans-serif", margin: 0, textAlign: "center" }}>
          Answers grounded in official IEEE SMC documents only · Cite-or-Abstain policy enforced · Not a substitute for official IEEE guidance
        </p>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 60%, 100% { opacity: 0.3; transform: scale(1); }
          30% { opacity: 1; transform: scale(1.2); }
        }
        textarea::placeholder { color: #B0B8C8; }
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #DDE3EE; border-radius: 99px; }
      `}</style>
    </div>
  );
}