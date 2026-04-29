"use client";

import { useState, useCallback } from "react";
import { Message, Source } from "@/types/chat";
import { MessageList } from "@/components/MessageList";
import { ChatInput } from "@/components/ChatInput";
import { SourcePanel } from "@/components/SourcePanel";
import { mockSources, mockResponse } from "@/lib/mockData";

// ─── Mock API call (replace with real fetch when backend is ready) ──────────
async function fetchMockAnswer(query: string): Promise<{ answer: string; sources: Source[] }> {
  await new Promise((r) => setTimeout(r, 1400)); // simulate latency
  return {
    answer: mockResponse.answer,
    sources: mockResponse.sources.slice(0, 3),
  };
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [activeCitationId, setActiveCitationId] = useState<number | null>(null);
  const [activeSource, setActiveSource] = useState<Source | null>(null);
  const [panelSources, setPanelSources] = useState<Source[]>([]);
  const [isPanelOpen, setIsPanelOpen] = useState(false);

  const handleCitationClick = useCallback((sourceId: number, sources: Source[]) => {
    const found = sources.find((s) => s.id === sourceId) ?? null;
    if (activeCitationId === sourceId && isPanelOpen) {
      // Toggle off
      setIsPanelOpen(false);
      setActiveCitationId(null);
      setActiveSource(null);
    } else {
      setActiveCitationId(sourceId);
      setActiveSource(found);
      setPanelSources(sources);
      setIsPanelOpen(true);
    }
  }, [activeCitationId, isPanelOpen]);

  const handleSourceSelect = useCallback((id: number) => {
    const found = panelSources.find((s) => s.id === id) ?? null;
    setActiveCitationId(id);
    setActiveSource(found);
  }, [panelSources]);

  const handleSend = useCallback(async (content: string) => {
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      timestamp: new Date(),
    };

    const loadingMsg: Message = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      timestamp: new Date(),
      isLoading: true,
    };

    setMessages((prev) => [...prev, userMsg, loadingMsg]);
    setIsLoading(true);

    try {
      const { answer, sources } = await fetchMockAnswer(content);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === loadingMsg.id
            ? { ...m, content: answer, sources, isLoading: false }
            : m
        )
      );
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === loadingMsg.id
            ? {
                ...m,
                content: "Error: Failed to fetch answer. Please try again.",
                isLoading: false,
              }
            : m
        )
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleClosePanel = useCallback(() => {
    setIsPanelOpen(false);
    setActiveCitationId(null);
    setActiveSource(null);
  }, []);

  return (
    <div className="h-screen flex flex-col bg-slate-50 overflow-hidden">
      {/* ── Top Nav ── */}
      <header className="flex-shrink-0 flex items-center justify-between px-6 py-3 bg-white border-b border-slate-200 shadow-sm z-10">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-ieee-blue flex items-center justify-center shadow-sm">
              <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="white" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
            <div>
              <h1 className="text-sm font-bold text-slate-800 leading-none">IEEE RAG Assistant</h1>
              <p className="text-[10px] text-slate-400 mt-0.5">Governance Document QA</p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-1.5 bg-green-50 border border-green-200 text-green-600 text-xs font-medium px-2.5 py-1 rounded-full">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
            Mock Mode
          </div>
          <button
            onClick={() => { setMessages([]); handleClosePanel(); }}
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-600 transition-colors px-2.5 py-1.5 rounded-lg hover:bg-slate-100"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
              Clear
          </button>
        </div>
      </header>

      {/* ── Main Layout ── */}
      <div className="flex-1 flex overflow-hidden">
        {/* ── Chat Area ── */}
        <div className={`flex flex-col flex-1 min-w-0 transition-all duration-300 ${isPanelOpen ? "lg:mr-0" : ""}`}>
          <MessageList
            messages={messages}
            activeCitationId={activeCitationId}
            onCitationClick={handleCitationClick}
          />
          <ChatInput onSend={handleSend} isLoading={isLoading} />
        </div>

        {/* ── Source Panel (slide in from right) ── */}
        <div
          className={`
            flex-shrink-0 border-l border-slate-200 bg-white overflow-hidden
            transition-all duration-300 ease-in-out
            ${isPanelOpen ? "w-full sm:w-80 lg:w-96 opacity-100" : "w-0 opacity-0"}
          `}
        >
          {isPanelOpen && (
            <SourcePanel
              source={activeSource}
              allSources={panelSources}
              activeId={activeCitationId}
              onClose={handleClosePanel}
              onSelect={handleSourceSelect}
            />
          )}
        </div>
      </div>
    </div>
  );
}