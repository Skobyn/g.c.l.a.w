"use client";

/**
 * /admin/user — Shared user profile.
 *
 * Edits the single ``user.md`` file injected as "# About the User" into
 * every agent's system prompt. Stable facts only (name, role, timezone,
 * communication preferences); evolving preferences live in Memory Bank.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";

function UserProfileContent() {
  const { getIdToken } = useAuth();
  const api = useMemo(() => createApiClient(getIdToken), [getIdToken]);

  const [content, setContent] = useState("");
  const [baseline, setBaseline] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getUserProfile();
      setContent(res.content);
      setBaseline(res.content);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load profile");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  const dirty = content !== baseline;

  async function save() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await api.updateUserProfile(content);
      setBaseline(content);
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex h-full flex-col bg-ink-900 text-paper">
      <header className="hairline-b px-8 pt-6 pb-5">
        <div className="label-caps mb-1.5">§ 12 · USER</div>
        <h1 className="font-display text-[30px] italic leading-none">
          About the User
        </h1>
        <p className="mt-2 max-w-2xl font-body text-[13px] text-paper-60">
          Shared context injected as <span className="font-mono">#&nbsp;About&nbsp;the&nbsp;User</span>{" "}
          into every agent&apos;s system prompt. Keep it to stable facts —
          name, role, timezone, communication preferences. Evolving
          preferences live in Memory Bank and are injected separately.
        </p>
      </header>

      <main className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-400 border-t-transparent" />
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-4">
            {error && (
              <div className="rounded-md border border-red-700 bg-red-900/20 px-3 py-2 text-sm text-red-300">
                {error}
              </div>
            )}
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              spellCheck={false}
              className="min-h-[480px] w-full rounded-md border border-slate-700 bg-slate-950 p-4 font-mono text-[13px] leading-relaxed text-slate-200 focus:border-indigo-500 focus:outline-none"
              placeholder="# About the User&#10;&#10;Stable facts about who the user is…"
            />
            <div className="flex items-center justify-between">
              <p className="text-[11px] text-paper-40">
                {content.length.toLocaleString()} chars
                {dirty && <span className="ml-2 text-amber-400">• unsaved</span>}
                {saved && <span className="ml-2 text-green-400">• saved</span>}
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setContent(baseline)}
                  disabled={!dirty || saving}
                  className="rounded-md border border-slate-600 px-4 py-1.5 text-sm text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                >
                  Reset
                </button>
                <button
                  type="button"
                  onClick={save}
                  disabled={!dirty || saving}
                  className="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                >
                  {saving ? "Saving…" : "Save"}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default function UserProfilePage() {
  return (
    <AppShell>
      <UserProfileContent />
    </AppShell>
  );
}
