"use client";

/**
 * Inline soul file editor for an agent.
 * Fetches the soul file content and allows saving changes.
 */

import { useState, useEffect, useCallback } from "react";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";

interface SoulEditorProps {
  agentName: string;
}

export function SoulEditor({ agentName }: SoulEditorProps) {
  const { getIdToken } = useAuth();
  const [content, setContent] = useState<string>("");
  const [original, setOriginal] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const fetchSoul = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const api = createApiClient(getIdToken);
      const soul = await api.getSoulFile(agentName);
      setContent(soul.content);
      setOriginal(soul.content);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load soul file");
    } finally {
      setLoading(false);
    }
  }, [agentName, getIdToken]);

  useEffect(() => {
    fetchSoul();
  }, [fetchSoul]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const api = createApiClient(getIdToken);
      await api.updateSoulFile(agentName, content);
      setOriginal(content);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save soul file");
    } finally {
      setSaving(false);
    }
  };

  const isDirty = content !== original;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-6">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {error && (
        <p className="text-sm text-red-400">{error}</p>
      )}
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={8}
        className="w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 font-mono text-sm text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        placeholder="Soul overlay content..."
      />
      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving || !isDirty}
          className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {saving ? "Saving..." : "Save"}
        </button>
        {saved && (
          <span className="text-sm text-green-400">Saved successfully</span>
        )}
        {isDirty && !saving && (
          <span className="text-sm text-slate-400">Unsaved changes</span>
        )}
      </div>
    </div>
  );
}
