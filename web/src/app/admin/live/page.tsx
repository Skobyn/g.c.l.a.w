"use client";

/**
 * Admin page: Live agent cockpit (session-scoped).
 *
 * Shows a chat session's live activity: a session-wide roll-up
 * (total tokens, total cost, turn count), a NowPlaying row for the
 * currently-active turn, and a timeline of turns within that session
 * (model / agent / tokens / cost / duration / status, newest first).
 *
 * URL: /admin/live?session=<session_id>
 * Legacy alias: ?run_id=<session_id> still works.
 */

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { AppShell } from "@/components/layout/app-shell";
import { useAuth } from "@/contexts/auth-context";
import { ContextGauge } from "@/components/admin/live/ContextGauge";
import { CostTicker } from "@/components/admin/live/CostTicker";
import { NowPlayingCard } from "@/components/admin/live/NowPlayingCard";
import { TokenMeter } from "@/components/admin/live/TokenMeter";
import { SessionTimeline } from "@/components/admin/live/SessionTimeline";
import { useRunDoc } from "@/hooks/useRunDoc";
import { useSessionTurns } from "@/hooks/useSessionTurns";

function formatCost(n: number): string {
  if (n === 0) return "$0.0000";
  if (n < 0.001) return "<$0.001";
  return `$${n.toFixed(4)}`;
}

function formatTokens(n: number): string {
  if (n >= 10_000) return `${(n / 1000).toFixed(1)}k`;
  return n.toLocaleString();
}

function LiveContent() {
  const { user } = useAuth();
  const params = useSearchParams();
  const urlSession =
    params?.get("session") ?? params?.get("run_id") ?? "";

  const [sessionId, setSessionId] = useState<string>(urlSession);
  useEffect(() => {
    if (urlSession) setSessionId(urlSession);
  }, [urlSession]);

  const run = useRunDoc(user?.uid ?? null, sessionId || null);
  const { turns, loaded, totals } = useSessionTurns(
    user?.uid ?? null,
    sessionId || null,
  );

  const onSubmit = useCallback(
    (ev: React.FormEvent<HTMLFormElement>) => {
      ev.preventDefault();
      const input = (ev.currentTarget.elements.namedItem(
        "sid",
      ) as HTMLInputElement) || null;
      if (input) setSessionId(input.value.trim());
    },
    [],
  );

  const rollup = useMemo(
    () => (
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile label="TURNS" value={String(totals.turn_count)} />
        <StatTile
          label="TOKENS IN"
          value={formatTokens(totals.tokens_in)}
        />
        <StatTile
          label="TOKENS OUT"
          value={formatTokens(totals.tokens_out)}
        />
        <StatTile
          label="SESSION COST"
          value={formatCost(totals.cost_usd)}
          accent
        />
      </div>
    ),
    [totals],
  );

  return (
    <div className="space-y-4 p-4">
      <form
        onSubmit={onSubmit}
        className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900/60 px-3 py-2"
      >
        <label
          htmlFor="sid"
          className="text-[11px] font-semibold uppercase tracking-wide text-slate-400"
        >
          Session ID
        </label>
        <input
          id="sid"
          name="sid"
          defaultValue={sessionId}
          placeholder="session_id (from the chat header)"
          className="flex-1 rounded bg-slate-800 px-2 py-1 text-sm text-slate-100 placeholder:text-slate-500"
        />
        <button
          type="submit"
          className="rounded bg-emerald-600 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-500"
        >
          Watch
        </button>
      </form>

      {!sessionId && (
        <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-6 text-sm text-slate-400">
          Paste a session ID above, or click the{" "}
          <code className="rounded bg-slate-800 px-1 text-slate-300">
            LIVE
          </code>{" "}
          link in the chat header to watch the active session. URL:{" "}
          <code className="rounded bg-slate-800 px-1 text-slate-300">
            /admin/live?session=…
          </code>
        </div>
      )}

      {sessionId && (
        <>
          {rollup}

          <div className="grid gap-4 md:grid-cols-2">
            <NowPlayingCard run={run} />
            <ContextGauge run={run} />
            <TokenMeter run={run} />
            <CostTicker run={run} />
          </div>

          <SessionTimeline turns={turns} loaded={loaded} />
        </>
      )}
    </div>
  );
}

function StatTile({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 px-4 py-3">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
        {label}
      </div>
      <div
        className={`mt-1 font-mono text-2xl tabular-nums ${
          accent ? "text-emerald-300" : "text-slate-100"
        }`}
      >
        {value}
      </div>
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
