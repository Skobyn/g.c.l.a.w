"use client";

/**
 * Memory search tab: text input that queries the search endpoint
 * and renders results as MemoryCard items.
 */

import { useState, useCallback } from "react";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";
import { MemoryCard } from "./memory-card";
import type { MemoryEntry } from "@/types";

export function MemorySearch() {
  const { getIdToken } = useAuth();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MemoryEntry[]>([]);
  const [searched, setSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingFact, setDeletingFact] = useState<string | null>(null);

  const handleSearch = useCallback(async () => {
    const trimmed = query.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    try {
      const api = createApiClient(getIdToken);
      const data = await api.searchMemories(trimmed);
      setResults(data);
      setSearched(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }, [query, getIdToken]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
  };

  const handleDelete = async (fact: string) => {
    setDeletingFact(fact);
    try {
      const api = createApiClient(getIdToken);
      await api.deleteMemory(fact);
      setResults((prev) => prev.filter((m) => m.fact !== fact));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete memory");
    } finally {
      setDeletingFact(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Search bar */}
      <div className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Search memories..."
          className="flex-1 rounded-md border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
        <button
          onClick={handleSearch}
          disabled={loading || !query.trim()}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors"
        >
          {loading ? "Searching..." : "Search"}
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-red-700 bg-red-900/30 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Results */}
      {searched && (
        <div>
          <p className="text-xs text-slate-400 mb-3">
            {results.length} result{results.length !== 1 ? "s" : ""} for &ldquo;{query}&rdquo;
          </p>
          {results.length === 0 ? (
            <p className="text-sm text-slate-500 italic">No matching memories found.</p>
          ) : (
            <div className="space-y-2">
              {results.map((memory, i) => (
                <MemoryCard
                  key={`${memory.fact}-${i}`}
                  memory={memory}
                  onDelete={handleDelete}
                  deleting={deletingFact === memory.fact}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
