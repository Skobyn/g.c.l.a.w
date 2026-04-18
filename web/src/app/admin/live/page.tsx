"use client";

/**
 * Admin page: Live agent cockpit.
 *
 * Subscribes to the Firestore /users/{uid}/agent_runs/{runId} doc the
 * backend LiveSpanProcessor writes (Phase 4). Shows which agent is
 * active, which model, tokens consumed, context-window utilisation %,
 * and running session cost.
 *
 * Run-ID selection: the URL query string `?run_id=<id>` wins; otherwise
 * the user pastes a run/session ID into the input. A typical value is
 * the chat session_id — wire your chat UI to link here once you have
 * the layout settled.
 */

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { useAuth } from "@/contexts/auth-context";
import { ContextGauge } from "@/components/admin/live/ContextGauge";
import { CostTicker } from "@/components/admin/live/CostTicker";
import { NowPlayingCard } from "@/components/admin/live/NowPlayingCard";
import { TokenMeter } from "@/components/admin/live/TokenMeter";
import { useRunDoc } from "@/hooks/useRunDoc";

function LiveContent() {
  const { user } = useAuth();
  const params = useSearchParams();
  const urlRun = params?.get("run_id") ?? "";

  const [runId, setRunId] = useState<string>(urlRun);
  useEffect(() => {
    if (urlRun) setRunId(urlRun);
  }, [urlRun]);

  const run = useRunDoc(user?.uid ?? null, runId || null);

  const onSubmit = useCallback(
    (ev: React.FormEvent<HTMLFormElement>) => {
      ev.preventDefault();
      const input = (ev.currentTarget.elements.namedItem(
        "rid",
      ) as HTMLInputElement) || null;
      if (input) setRunId(input.value.trim());
    },
    [],
  );

  return (
    <div className="space-y-4 p-4">
      <form
        onSubmit={onSubmit}
        className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2"
      >
        <label
          htmlFor="rid"
          className="text-[11px] font-semibold uppercase tracking-wide text-slate-400"
        >
          Run ID
        </label>
        <input
          id="rid"
          name="rid"
          defaultValue={runId}
          placeholder="session/run id (e.g. chat session_id)"
          className="flex-1 rounded bg-slate-800 px-2 py-1 text-sm text-slate-100 placeholder:text-slate-500"
        />
        <button
          type="submit"
          className="rounded bg-emerald-600 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-500"
        >
          Watch
        </button>
      </form>

      {!runId && (
        <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-6 text-sm text-slate-400">
          Paste a run ID above (or append{" "}
          <code className="rounded bg-slate-800 px-1 text-slate-300">
            ?run_id=…
          </code>{" "}
          to the URL) to start watching.
        </div>
      )}

      {runId && (
        <div className="grid gap-4 md:grid-cols-2">
          <NowPlayingCard run={run} />
          <ContextGauge run={run} />
          <TokenMeter run={run} />
          <CostTicker run={run} />
        </div>
      )}
    </div>
  );
}

export default function LivePage() {
  return (
    <AppShell>
      <Suspense
        fallback={
          <div className="p-4 text-sm text-slate-400">Loading…</div>
        }
      >
        <LiveContent />
      </Suspense>
    </AppShell>
  );
}
