"use client";

import { useState, useRef, useEffect, KeyboardEvent } from "react";

interface ChatInputProps {
  onSend: (message: string) => void;
  isLoading: boolean;
}

export function ChatInput({ onSend, isLoading }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  }, [value]);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setValue("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="border-t border-slate-200 bg-white/80 backdrop-blur-sm px-4 py-4">
      <div className={`flex items-end gap-3 rounded-2xl border-2 bg-white px-4 py-3 shadow-sm transition-all duration-200 ${
        isLoading ? "border-slate-200" : "border-slate-200 focus-within:border-ieee-blue focus-within:shadow-md focus-within:shadow-ieee-blue/10"
      }`}>
        {/* Textarea */}
        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask me anything about IEEE documents..."
          disabled={isLoading}
          className="flex-1 resize-none bg-transparent text-sm text-slate-700 placeholder-slate-400 outline-none leading-relaxed min-h-[24px] max-h-[160px] disabled:opacity-50"
        />

        {/* Send / Loading button */}
        <button
          onClick={handleSubmit}
          disabled={!value.trim() || isLoading}
          className={`flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200 ${
            value.trim() && !isLoading
              ? "bg-ieee-blue text-white hover:bg-ieee-blue/90 shadow-sm hover:shadow-md hover:shadow-ieee-blue/25 active:scale-95"
              : "bg-slate-100 text-slate-400 cursor-not-allowed"
          }`}
          aria-label="Send message"
        >
          {isLoading ? (
            <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          )}
        </button>
      </div>

      <p className="mt-2 text-center text-[10px] text-slate-300">
        Press Enter to send · Press Shift+Enter for a newline · IEEE document sources are cited in the answer
      </p>
    </div>
  );
}