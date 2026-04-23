"use client";

/**
 * TaskDetailsModal — click a board task to see what the assignee
 * agent is actually doing.
 *
 * Shows:
 *   - Task header (title, assignee, priority, status)
 *   - Live state for IN_PROGRESS tasks (poll + SSE for task.* events)
 *   - Result summary (verbatim manager output) when completed
 *   - Failure reason when failed
 *   - Timeline of recent LLM + tool calls (from UsageEvent) within the
 *     task's time window — model/tokens/cost/tool/duration
 *
 * The modal is the board's window into sub-agent work. Before this
 * there was no way to see what research-mgr actually did — just that
 * it did something. Now: click the task, see the model calls that
 * produced the result, read the verbatim output.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useApiClient } from "@/lib/api-client";
import type { BoardTask, UsageEvent } from "@/types";

interface Props {
  task: BoardTask | null;
  onClose: () => void;
}

function fmtTime(iso: string | null | undefined): string {
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

function fmtDuration(ms: number | null | undefined): string {
  if (typeof ms !== "number" || ms <= 0) return "—";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60_000)}m ${Math.floor((ms % 60_000) / 1000)}s`;
}

function fmtCost(n: number | null | undefined): string {
  if (typeof n !== "number" || n === 0) return "—";
  if (n < 0.001) return "<$0.001";
  return `$${n.toFixed(4)}`;
}

function priorityGlyph(p: string): string {
  if (p === "high") return "◐";
  if (p === "medium") return "◎";
  return "·";
}

function priorityClass(p: string): string {
  if (p === "high") return "text-gold";
  if (p === "medium") return "text-signal-dim";
  return "text-paper-40";
}

function statusClass(s: string): string {
  if (s === "in_progress") return "text-signal animate-pulse";
  if (s === "done" || s === "completed") return "text-signal-dim";
  if (s === "failed") return "text-alert";
  if (s === "queued") return "text-paper-60";
  return "text-paper-40";
}

const POLL_MS = 2_000;

export function TaskDetailsModal({ task, onClose }: Props) {
  const api = useApiClient();
  const [events, setEvents] = useState<UsageEvent[]>([]);
  const [loadingEvents, setLoadingEvents] = useState(false);

  const taskActive = task?.status === "in_progress" || task?.status === "queued";

  // Fetch usage events in the task's time window. Poll while in-flight
  // so the user sees new tool/LLM calls as research-mgr makes them.
  const fetchEvents = useCallback(async () => {
    if (!task) return;
    setLoadingEvents(true);
    try {
      const since = task.created_at;
      const rows = await api.getUsageEvents({
        limit: 100,
        since: since ?? undefined,
      });
      setEvents(rows);
    } catch {
      // best-effort; leave list unchanged on error
    } finally {
      setLoadingEvents(false);
    }
  }, [api, task]);

  useEffect(() => {
    if (!task) return;
    void fetchEvents();
    if (!taskActive) return;
    const id = setInterval(fetchEvents, POLL_MS);
    return () => clearInterval(id);
  }, [task, taskActive, fetchEvents]);

  // ESC to close.
  useEffect(() => {
    if (!task) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [task, onClose]);

  const relevantEvents = useMemo(() => {
    if (!task) return [] as UsageEvent[];
    // Heuristic: show events for the task's assignee manager OR that
    // caller-chained through it. The UsageEvent has `caller` + `name`
    // (model/agent/tool name) — scope to recent events around the task
    // window. This is approximate; v2 will link via work_trace_id.
    const start = Date.parse(task.created_at || "") || 0;
    const end = Date.parse(task.updated_at || "") || Date.now();
    const window_end = end + 30_000; // 30s tail after last update
    return events.filter((e) => {
      const t = Date.parse(e.timestamp) || 0;
      if (t < start || t > window_end) return false;
      // Cheap relevance filter: task assignee matches the caller chain.
      const hay = `${e.caller ?? ""} ${e.name ?? ""}`.toLowerCase();
      if (task.assignee && hay.includes(task.assignee.toLowerCase())) return true;
      // Otherwise include anything recent inside the window (useful for
      // orchestrator LLM calls that produced the delegation).
      return true;
    });
  }, [events, task]);

  if (!task) return null;

  const summary = task.result?.summary ?? null;
  const rejectionNote = task.rejection_note ?? null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <section
        role="dialog"
        aria-labelledby="task-modal-title"
        className="w-full max-w-3xl max-h-[85vh] overflow-hidden rounded-lg border border-paper-08 bg-ink-900 shadow-2xl flex flex-col"
      >
        {/* Header */}
        <header className="border-b border-paper-08/40 px-6 py-4 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-paper-40">
              <span aria-hidden className={priorityClass(task.priority)}>
                {priorityGlyph(task.priority)}
              </span>
              <span className={priorityClass(task.priority)}>
                {task.priority}
              </span>
              <span>·</span>
              <span className={statusClass(task.status)}>{task.status}</span>
              <span>·</span>
              <span className="truncate">{task.assignee || "unassigned"}</span>
              <span>·</span>
              <span className="text-paper-40">{task.id}</span>
            </div>
            <h2
              id="task-modal-title"
              className="mt-1 font-display text-2xl italic text-paper leading-snug"
            >
              {task.title}
            </h2>
            {task.description && (
              <p className="mt-2 font-body text-[13px] text-paper-60 whitespace-pre-wrap">
                {task.description}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="btn-hair shrink-0"
            title="Close (Esc)"
          >
            ✕
          </button>
        </header>

        {/* Body (scrollable) */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">
          {/* Live state banner for in-flight */}
          {taskActive && (
            <div className="rounded border border-signal-dim/40 bg-signal/5 px-3 py-2 font-mono text-[11px] uppercase tracking-[0.14em] text-signal-dim">
              <span className="inline-block h-2 w-2 rounded-full bg-signal animate-pulse mr-2" />
              {task.status === "in_progress"
                ? "agent is working · polling every 2s"
                : "queued · waiting for assignee heartbeat"}
            </div>
          )}

          {/* Result — the verbatim manager output */}
          {summary && (
            <section>
              <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-paper-40 mb-1.5">
                ✓ RESULT
              </div>
              <pre className="whitespace-pre-wrap font-body text-[13px] leading-[1.6] text-paper-80 hairline-l pl-4 py-1">
                {summary}
              </pre>
            </section>
          )}

          {/* Failure reason */}
          {task.status === "failed" && rejectionNote && (
            <section>
              <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-alert mb-1.5">
                ✗ FAILED
              </div>
              <pre className="whitespace-pre-wrap font-body text-[13px] leading-[1.6] text-alert hairline-l pl-4 py-1">
                {rejectionNote}
              </pre>
            </section>
          )}

          {/* LLM + tool timeline */}
          <section>
            <div className="flex items-baseline justify-between font-mono text-[10px] uppercase tracking-[0.16em] text-paper-40 mb-1.5">
              <span>AGENT ACTIVITY · {relevantEvents.length}</span>
              {loadingEvents && <span>loading…</span>}
            </div>
            {relevantEvents.length === 0 ? (
              <p className="font-mono text-[11px] italic text-paper-40">
                No activity recorded yet for this task&apos;s time window.
              </p>
            ) : (
              <ul className="space-y-[2px] font-mono text-[12px]">
                {relevantEvents.map((e) => (
                  <li
                    key={e.id}
                    className="grid grid-cols-[auto_auto_minmax(0,1fr)_auto_auto_auto] items-baseline gap-3 py-[2px]"
                  >
                    <span className="text-paper-40 tabular-nums">
                      {fmtTime(e.timestamp)}
                    </span>
                    <span
                      className={`uppercase tracking-wider text-[10px] ${
                        e.kind === "model"
                          ? "text-signal-dim"
                          : e.kind === "tool"
                            ? "text-gold"
                            : e.kind === "skill"
                              ? "text-paper-60"
                              : "text-paper-40"
                      }`}
                    >
                      {e.kind}
                    </span>
                    <span className="min-w-0 truncate text-paper">
                      {e.name}
                      {e.caller && (
                        <span className="ml-2 text-paper-40">
                          · {e.caller}
                        </span>
                      )}
                      {e.error && (
                        <span className="ml-2 text-alert">
                          · {e.error.slice(0, 60)}
                        </span>
                      )}
                    </span>
                    <span className="text-paper-40 tabular-nums">
                      {typeof e.tokens_in === "number" && typeof e.tokens_out === "number"
                        ? `${e.tokens_in}↓ ${e.tokens_out}↑`
                        : ""}
                    </span>
                    <span className="text-signal-dim tabular-nums">
                      {fmtCost(e.cost_usd)}
                    </span>
                    <span className="text-paper-40 tabular-nums">
                      {fmtDuration(e.duration_ms)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Raw task metadata (collapsed) */}
          <details className="mt-2">
            <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.16em] text-paper-40 hover:text-paper">
              RAW TASK JSON
            </summary>
            <pre className="mt-2 whitespace-pre-wrap font-mono text-[11px] text-paper-60 hairline-l pl-4 py-1">
              {JSON.stringify(task, null, 2)}
            </pre>
          </details>
        </div>

        {/* Footer */}
        <footer className="border-t border-paper-08/40 px-6 py-3 flex items-center gap-3 text-[10px] font-mono uppercase tracking-[0.14em] text-paper-40">
          <span>
            created {fmtTime(task.created_at)} · updated{" "}
            {fmtTime(task.updated_at)}
          </span>
          <button
            type="button"
            onClick={() => void fetchEvents()}
            className="btn-hair ml-auto"
            title="Refresh usage events"
          >
            REFRESH
          </button>
        </footer>
      </section>
    </div>
  );
}
