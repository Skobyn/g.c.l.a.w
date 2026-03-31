"use client";

/**
 * Memory browse tab: lists all memories grouped by topic.
 */

import { useState, useEffect, useCallback } from "react";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";
import { MemoryCard } from "./memory-card";
import type { MemoryEntry } from "@/types";

export function MemoryList() {
  const { getIdToken } = useAuth();
  const [memories, setMemories] = useState<MemoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingFact, setDeletingFact] = useState<string | null>(null);

  const fetchMemories = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const api = createApiClient(getIdToken);
      const data = await api.listMemories();
      setMemories(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load memories");
    } finally {
      setLoading(false);
    }
  }, [getIdToken]);

  useEffect(() => {
    fetchMemories();
  }, [fetchMemories]);

  const handleDelete = async (fact: string) => {
    setDeletingFact(fact);
    try {
      const api = createApiClient(getIdToken);
      await api.deleteMemory(fact);
      setMemories((prev) => prev.filter((m) => m.fact !== fact));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete memory");
    } finally {
      setDeletingFact(null);
    }
  };

  // Group memories by topic
  const grouped = memories.reduce<Record<string, MemoryEntry[]>>((acc, mem) => {
    const topic = mem.topic || "Uncategorized";
    if (!acc[topic]) acc[topic] = [];
    acc[topic].push(mem);
    return acc;
  }, {});

  const topics = Object.keys(grouped).sort();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-400">
          {memories.length} memor{memories.length !== 1 ? "ies" : "y"} across {topics.length} topic{topics.length !== 1 ? "s" : ""}
        </p>
        <button
          onClick={fetchMemories}
          disabled={loading}
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 disabled:opacity-50 transition-colors"
        >
          <svg
            className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-red-700 bg-red-900/30 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {loading && memories.length === 0 ? (
        <div className="flex items-center justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-400 border-t-transparent" />
        </div>
      ) : memories.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-slate-500">
          <svg className="h-10 w-10 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          <p className="text-sm">No memories stored yet</p>
        </div>
      ) : (
        <div className="space-y-6">
          {topics.map((topic) => (
            <div key={topic}>
              <div className="flex items-center gap-2 mb-2">
                <h3 className="text-sm font-semibold text-indigo-400">{topic}</h3>
                <span className="text-xs text-slate-500">({grouped[topic].length})</span>
              </div>
              <div className="space-y-2">
                {grouped[topic].map((memory, i) => (
                  <MemoryCard
                    key={`${memory.fact}-${i}`}
                    memory={memory}
                    onDelete={handleDelete}
                    deleting={deletingFact === memory.fact}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
