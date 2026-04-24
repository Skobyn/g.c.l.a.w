"use client";

/**
 * RecentTranscripts — list the user's recent chat sessions and
 * inline-load the per-author transcript for any one of them.
 *
 * Sits at the bottom of the Observability page. Built on the
 * existing onSnapshot hooks (useRecentSessions + useSessionTurns +
 * useTurnMessages) so updates land live as agents speak.
 */

import { useState } from "react";
import { useRecentSessions } from "@/hooks/useRecentSessions";
import { useSessionTurns } from "@/hooks/useSessionTurns";
import { SessionTimeline } from "@/components/admin/live/SessionTimeline";

interface Props {
  uid: string | null | undefined;
}

function fmtTime(iso: string | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      hour12: false,
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function statusClass(s: string | undefined): string {
  const v = (s ?? "").toUpperCase();
  if (v === "ERROR") return "text-red-400";
  if (v === "OK" || v === "DONE") return "text-emerald-300";
  if (v === "UNSET" || !v) return "text-slate-500";
  return "text-amber-300";
}

export function RecentTranscripts({ uid }: Props) {
  const { sessions, loaded } = useRecentSessions(uid ?? null, 10);
  const [active, setActive] = useState<string | null>(null);
  const { turns, loaded: turnsLoaded } = useSessionTurns(uid ?? null, active);

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60">
      <div className="flex items-center justify-between border-b border-slate-700 px-4 py-2 text-sm font-semibold text-slate-200">
        <span>
          Recent Transcripts
          {sessions.length > 0 && (
            <span className="ml-1 font-normal text-slate-500">
              ({sessions.length})
            </span>
          )}
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-slate-500">
          Per-author capture · redacted
        </span>
      </div>

      {!loaded ? (
        <div className="px-4 py-6 text-center text-sm text-slate-500">
          Loading recent sessions…
        </div>
      ) : sessions.length === 0 ? (
        <div className="px-4 py-6 text-center text-sm text-slate-500">
          No recent sessions captured yet. Start a chat — turns appear here
          with their per-author transcripts.
        </div>
      ) : (
        <ul>
          {sessions.map((s) => {
            const isActive = active === s.id;
            return (
              <li key={s.id} className="border-b border-slate-800 last:border-b-0">
                <button
                  type="button"
                  onClick={() => setActive(isActive ? null : s.id)}
                  className="grid w-full grid-cols-[auto_minmax(0,1fr)_auto_auto_auto] items-baseline gap-3 px-4 py-2 text-left font-mono text-[12px] text-slate-200 hover:bg-slate-800/40"
                >
                  <span aria-hidden className="text-slate-500 text-[10px]">
                    {isActive ? "▾" : "▸"}
                  </span>
                  <div className="min-w-0 truncate">
                    <span className="text-slate-300 truncate">{s.id}</span>
                    {s.active_agent && (
                      <>
                        <span className="mx-2 text-slate-500">·</span>
                        <span className="text-emerald-300">
                          {s.active_agent}
                        </span>
                      </>
                    )}
                  </div>
                  <span className="text-slate-400 text-[11px]">
                    {s.model_id ?? "—"}
                  </span>
                  <span className={`text-[10px] uppercase tracking-wider ${statusClass(s.status)}`}>
                    {s.status ?? "—"}
                  </span>
                  <span className="text-slate-500 tabular-nums text-[10px]">
                    {fmtTime(s.updated_at)}
                  </span>
                </button>

                {isActive && (
                  <div className="border-t border-slate-800 bg-slate-950/40 p-3">
                    <SessionTimeline
                      turns={turns}
                      loaded={turnsLoaded}
                      uid={uid ?? null}
                      sessionId={active}
                    />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
