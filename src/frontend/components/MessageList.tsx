"use client";

import { Message, Source } from "@/types/chat";
import { CitationBadge } from "./CitationBadge";
import { useEffect, useRef } from "react";

interface MessageListProps {
  messages: Message[];
  activeCitationId: number | null;
  onCitationClick: (sourceId: number, sources: Source[]) => void;
}

function parseContentWithCitations(
  content: string,
  sources: Source[],
  activeCitationId: number | null,
  onCitationClick: (id: number, sources: Source[]) => void
): React.ReactNode[] {
  const parts = content.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (match) {
      const id = parseInt(match[1]);
      return (
        <CitationBadge
          key={i}
          sourceId={id}
          isActive={activeCitationId === id}
          onClick={(sid) => onCitationClick(sid, sources)}
        />
      );
    }
    // Render **bold** text
    const boldParts = part.split(/(\*\*[^*]+\*\*)/g);
    return boldParts.map((bp, j) => {
      if (bp.startsWith("**") && bp.endsWith("**")) {
        return <strong key={`${i}-${j}`} className="font-semibold text-slate-800">{bp.slice(2, -2)}</strong>;
      }
      // Handle newlines
      return bp.split("\n").map((line, k, arr) => (
        <span key={`${i}-${j}-${k}`}>
          {line}
          {k < arr.length - 1 && <br />}
        </span>
      ));
    });
  });
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 py-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-2 h-2 rounded-full bg-ieee-blue/40 animate-bounce"
          style={{ animationDelay: `${i * 150}ms`, animationDuration: "800ms" }}
        />
      ))}
    </div>
  );
}

export function MessageList({ messages, activeCitationId, onCitationClick }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-6 py-20 px-6 text-center">
        <div className="w-16 h-16 rounded-2xl bg-ieee-blue/10 flex items-center justify-center">
          <svg className="w-8 h-8 text-ieee-blue" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </div>
        <div>
          <h2 className="text-xl font-bold text-slate-700 mb-2">IEEE Governance Assistant</h2>
          <p className="text-slate-400 text-sm max-w-sm leading-relaxed">
            Ask questions about IEEE and SMCS governance documents. Answers include precise source citations.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 justify-center max-w-md">
          {[
            "Board composition?",
            "Executive Director role?",
            "What is SMCS Technical Committee?",
            "Membership requirements?",
          ].map((q) => (
            <span key={q} className="px-3 py-1.5 rounded-full bg-slate-100 text-slate-500 text-xs font-medium border border-slate-200 cursor-default hover:border-ieee-blue/40 hover:text-ieee-blue transition-colors">
              {q}
            </span>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
      {messages.map((msg) => (
        <div key={msg.id} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
          {/* Avatar */}
          <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shadow-sm ${
            msg.role === "user"
              ? "bg-slate-200 text-slate-600"
              : "bg-ieee-blue text-white"
          }`}>
            {msg.role === "user" ? "U" : "AI"}
          </div>

          <div className={`max-w-[78%] ${msg.role === "user" ? "items-end" : "items-start"} flex flex-col gap-1`}>
            {/* Bubble */}
            <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
              msg.role === "user"
                ? "bg-ieee-blue text-white rounded-tr-sm"
                : "bg-white border border-slate-200 text-slate-700 rounded-tl-sm"
            }`}>
              {msg.isLoading ? (
                <TypingIndicator />
              ) : (
                <p className="whitespace-pre-wrap">
                  {msg.sources && msg.sources.length > 0
                    ? parseContentWithCitations(msg.content, msg.sources, activeCitationId, onCitationClick)
                    : msg.content}
                </p>
              )}
            </div>

            {/* Source chips below assistant messages */}
            {msg.role === "assistant" && msg.sources && msg.sources.length > 0 && !msg.isLoading && (
              <div className="flex flex-wrap gap-1.5 mt-1 px-1">
                {msg.sources.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => onCitationClick(s.id, msg.sources!)}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border transition-all duration-150 ${
                      activeCitationId === s.id
                        ? "bg-ieee-blue text-white border-ieee-blue"
                        : "bg-white text-slate-500 border-slate-200 hover:border-ieee-blue/50 hover:text-ieee-blue"
                    }`}
                  >
                    <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold ${
                      activeCitationId === s.id ? "bg-white/20" : "bg-ieee-blue/10 text-ieee-blue"
                    }`}>{s.id}</span>
                    <span className="max-w-[100px] truncate">{s.doc.replace(".pdf", "")}</span>
                    <span className="opacity-60">p.{s.page}</span>
                  </button>
                ))}
              </div>
            )}

            {/* Timestamp */}
            <span className="text-[10px] text-slate-300 px-1">
              {msg.timestamp.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
            </span>
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}