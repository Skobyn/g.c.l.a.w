"use client";

/**
 * SessionTimeline — turn-by-turn list for the /admin/live session view.
 *
 * Renders each turn's model, agent, tokens in/out, cost, duration,
 * status. Newest turn at the top. Hairline-bordered rows, tabular-nums,
 * phosphor dot that pulses while a turn is still progressing (status
 * != OK/DONE/ERROR).
 */

import type { TurnDoc } from "@/hooks/useSessionTurns";

interface Props {
  turns: TurnDoc[];
  loaded: boolean;
}

function fmtTokens(n: number | null | undefined): string {
  if (typeof n !== "number") return "—";
  if (n >= 10_000) return `${(n / 1000).toFixed(1)}k`;
  return n.toLocaleString();
}

function fmtCost(n: number | null | undefined): string {
  if (typeof n !== "number" || n === 0) return "—";
  if (n < 0.001) return "<$0.001";
  return `$${n.toFixed(4)}`;
}

function fmtDuration(startIso: string | undefined, endIso: string | undefined): string {
  if (!startIso) return "—";
  const start = Date.parse(startIso);
  const end = endIso ? Date.parse(endIso) : Date.now();
  if (!isFinite(start) || !isFinite(end)) return "—";
  const ms = end - start;
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60_000)}m ${Math.floor((ms % 60_000) / 1000)}s`;
}

function fmtTime(iso: string | undefined): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function isLive(t: TurnDoc): boolean {
  const s = (t.status ?? "").toUpperCase();
  return s !== "OK" && s !== "DONE" && s !== "ERROR" && s !== "UNSET";
}

export function SessionTimeline({ turns, loaded }: Props) {
  if (!loaded) {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-4 text-sm text-slate-400">
        Loading turns…
      </div>
    );
  }
  if (turns.length === 0) {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-900/60 p-4 text-sm text-slate-400">
        No turns yet for this session. Once an agent runs, each turn
        will show up here with its model, tokens, cost, and status.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60">
      <div className="border-b border-slate-700 px-4 py-2 font-mono text-[10px] uppercase tracking-[0.16em] text-slate-400">
        TURN TIMELINE · {turns.length}
      </div>
      <ul>
        {turns.map((turn) => {
          const live = isLive(turn);
          const failed = (turn.status ?? "").toUpperCase() === "ERROR";
          return (
            <li
              key={turn.turn_id ?? turn.last_trace_id ?? ""}
              className="grid grid-cols-[auto_minmax(0,1fr)_auto_auto_auto_auto] items-baseline gap-3 border-b border-slate-800 px-4 py-2 last:border-b-0 font-mono text-[12px] text-slate-200"
            >
              <span
                aria-hidden
                className={`mt-[6px] h-[6px] w-[6px] rounded-full ${
                  failed
                    ? "bg-red-500"
                    : live
                      ? "bg-emerald-400 animate-pulse"
                      : "bg-slate-600"
                }`}
              />
              <div className="min-w-0 truncate">
                <span className="text-emerald-300">
                  {turn.active_agent ?? "—"}
                </span>
                <span className="mx-2 text-slate-500">·</span>
                <span className="text-slate-300">
                  {turn.model_id ?? "—"}
                </span>
                {turn.tool_in_flight?.name && (
                  <>
                    <span className="mx-2 text-slate-500">·</span>
                    <span className="text-amber-300">
                      tool: {turn.tool_in_flight.name}
                    </span>
                  </>
                )}
              </div>
              <span className="text-slate-400 tabular-nums">
                {fmtTokens(turn.tokens?.in)}↓ {fmtTokens(turn.tokens?.out)}↑
              </span>
              <span className="text-emerald-200 tabular-nums">
                {fmtCost(turn.cost_usd_turn ?? turn.cost_usd_session)}
              </span>
              <span className="text-slate-500 tabular-nums">
                {fmtDuration(turn.started_at, turn.updated_at)}
              </span>
              <span className="text-slate-500 text-[10px] tabular-nums">
                {fmtTime(turn.started_at ?? turn.updated_at)}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
