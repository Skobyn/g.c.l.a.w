"use client";

/**
 * Card for a single memory entry.
 * Shows fact text, topic, optional distance score, and a delete button.
 */

import type { MemoryEntry } from "@/types";

interface MemoryCardProps {
  memory: MemoryEntry;
  onDelete: (fact: string) => void;
  deleting: boolean;
}

export function MemoryCard({ memory, onDelete, deleting }: MemoryCardProps) {
  return (
    <div className="flex items-start gap-3 rounded-md border border-slate-700 bg-slate-800 px-4 py-3">
      <div className="flex-1 min-w-0">
        <p className="text-sm text-slate-200 leading-relaxed">{memory.fact}</p>
        <div className="flex flex-wrap items-center gap-3 mt-2">
          <span className="rounded-full bg-indigo-900/50 px-2 py-0.5 text-xs text-indigo-300">
            {memory.topic}
          </span>
          {memory.score !== null && (
            <span className="text-xs text-slate-500">
              score: {memory.score.toFixed(3)}
            </span>
          )}
          {memory.update_time && (
            <span className="text-xs text-slate-500">
              {new Date(memory.update_time).toLocaleDateString()}
            </span>
          )}
        </div>
      </div>
      <button
        onClick={() => onDelete(memory.fact)}
        disabled={deleting}
        className="flex-shrink-0 rounded p-1.5 text-slate-500 hover:text-red-400 hover:bg-red-900/30 disabled:opacity-50 transition-colors"
        title="Delete memory"
      >
        {deleting ? (
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-red-400 border-t-transparent" />
        ) : (
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
        )}
      </button>
    </div>
  );
}
