"use client";

import { CitationProps } from "@/types/chat";

export function CitationBadge({ sourceId, onClick, isActive }: CitationProps) {
  return (
    <button
      onClick={() => onClick(sourceId)}
      className={`inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold mx-0.5 align-super transition-all duration-200 cursor-pointer border ${
        isActive
          ? "bg-ieee-blue text-white border-ieee-blue shadow-sm shadow-ieee-blue/30"
          : "bg-ieee-blue/10 text-ieee-blue border-ieee-blue/30 hover:bg-ieee-blue hover:text-white hover:border-ieee-blue"
      }`}
      aria-label={`Source ${sourceId}`}
    >
      {sourceId}
    </button>
  );
}