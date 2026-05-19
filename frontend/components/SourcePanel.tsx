"use client";

import { Source } from "@/types/chat";
import { useEffect } from "react";

interface SourcePanelProps {
  source: Source | null;
  allSources: Source[];
  activeId: number | null;
  onClose: () => void;
  onSelect: (id: number) => void;
}

export function SourcePanel({
  source,
  allSources,
  activeId,
  onClose,
  onSelect,
}: SourcePanelProps) {
  // Close on Escape key
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  if (!source) return null;

  const fileIcon = (doc: string) => {
    if (doc.endsWith(".pdf")) return "📄";
    if (doc.endsWith(".docx")) return "📝";
    return "📁";
  };

  return (
    <div className="flex flex-col h-full bg-white border-l border-slate-200">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 bg-slate-50/80">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-5 rounded-full bg-ieee-blue" />
          <span className="text-sm font-semibold text-slate-700 tracking-wide uppercase">
            Sources
          </span>
          <span className="ml-1 bg-ieee-blue/10 text-ieee-blue text-xs font-bold px-2 py-0.5 rounded-full">
            {allSources.length}
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200 transition-colors"
          aria-label="Close sources panel"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Source tabs */}
      <div className="flex gap-1.5 px-4 py-3 border-b border-slate-100 overflow-x-auto flex-shrink-0">
        {allSources.map((s) => (
          <button
            key={s.id}
            onClick={() => onSelect(s.id)}
            className={`flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 ${
              activeId === s.id
                ? "bg-ieee-blue text-white shadow-sm"
                : "bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-700"
            }`}
          >
            <span>{s.id}</span>
            <span className="max-w-[80px] truncate opacity-80">{s.doc.replace(".pdf", "")}</span>
          </button>
        ))}
      </div>

      {/* Source detail */}
      <div className="flex-1 overflow-y-auto px-5 py-5">
        <div className="mb-4">
          <div className="flex items-start gap-3">
            <span className="text-2xl">{fileIcon(source.doc)}</span>
            <div>
              <h3 className="font-bold text-slate-800 text-sm leading-snug">{source.doc}</h3>
              <div className="flex items-center gap-2 mt-1">
                <span className="inline-flex items-center gap-1 bg-slate-100 text-slate-500 text-xs px-2 py-0.5 rounded-md font-medium">
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  Page {source.page}
                </span>
                <span className="inline-flex items-center gap-1 bg-ieee-blue/10 text-ieee-blue text-xs px-2 py-0.5 rounded-md font-semibold">
                  Citation [{source.id}]
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Excerpt */}
        <div className="relative">
          <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-ieee-blue rounded-full" />
          <div className="pl-4">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Excerpt</p>
            <p className="text-sm text-slate-700 leading-relaxed font-serif">
              &ldquo;{source.text}&rdquo;
            </p>
          </div>
        </div>

        {/* View button */}
        <button className="mt-6 w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl border-2 border-ieee-blue/20 text-ieee-blue text-sm font-semibold hover:bg-ieee-blue hover:text-white hover:border-ieee-blue transition-all duration-200 group">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
          View Full Document
        </button>
      </div>
    </div>
  );
}