"use client";

/**
 * BoardSummaryCard — live board-state widget that replaces the previous
 * BackgroundActivityStrip in the chat view. Shows:
 *
 *   ● BOARD · 3 in-flight · 2 queued · 12 done  (summary bar, always visible)
 *
 * Click any phase chip to expand a breakdown of tasks grouped by assignee
 * under that phase. Live-updates from the useUserEvents SSE stream. The
 * summary bar is the landing target for the binary-stream animation
 * triggered when the orchestrator delegates a task (see
 * useDelegationStream / DelegationStreamOverlay).
 *
 * Design ref: phosphor observatory — tiny caps, tabular-nums, phosphor-dot
 * on the left that pulses when anything is running.
 */

import { forwardRef, useMemo, useState } from "react";
import type { BackgroundTaskItem } from "@/lib/use-user-events";

type Phase = "running" | "queued" | "done" | "failed";

const PHASE_LABEL: Record<Phase, string> = {
  running: "IN-FLIGHT",
  queued: "QUEUED",
  done: "DONE",
  failed: "FAILED",
};

const PHASE_CLASS: Record<Phase, string> = {
  running: "text-signal",
  queued: "text-paper-60",
  done: "text-signal-dim",
  failed: "text-alert",
};

interface Props {
  items: BackgroundTaskItem[];
  inFlight: number;
  queued: number;
}

function priorityGlyph(p: BackgroundTaskItem["priority"]): string {
  if (p === "high") return "◐";
  if (p === "medium") return "◎";
  return "·";
}

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

/** Group tasks by assignee/manager, returning counts + sorted task list. */
function groupByAssignee(tasks: BackgroundTaskItem[]) {
  const by = new Map<string, BackgroundTaskItem[]>();
  for (const t of tasks) {
    const k = t.manager || "(unassigned)";
    const arr = by.get(k) ?? [];
    arr.push(t);
    by.set(k, arr);
  }
  // Sort each group newest-first.
  for (const arr of by.values()) {
    arr.sort((a, b) => b.lastEventTime.localeCompare(a.lastEventTime));
  }
  // Sort managers by count desc, then name.
  return Array.from(by.entries()).sort((a, b) => {
    const d = b[1].length - a[1].length;
    return d !== 0 ? d : a[0].localeCompare(b[0]);
  });
}

export const BoardSummaryCard = forwardRef<HTMLDivElement, Props>(
  function BoardSummaryCard({ items, inFlight, queued }, ref) {
    const [openPhase, setOpenPhase] = useState<Phase | null>(null);

    const phaseGroups = useMemo(() => {
      const buckets: Record<Phase, BackgroundTaskItem[]> = {
        running: [],
        queued: [],
        done: [],
        failed: [],
      };
      for (const t of items) buckets[t.status].push(t);
      return buckets;
    }, [items]);

    const counts: Record<Phase, number> = {
      running: phaseGroups.running.length || inFlight,
      queued: phaseGroups.queued.length || queued,
      done: phaseGroups.done.length,
      failed: phaseGroups.failed.length,
    };

    const hasAnyInFlight = counts.running > 0;

    return (
      <div
        ref={ref}
        data-testid="board-summary-card"
        className="hairline-t bg-ink-900"
      >
        {/* Always-visible summary row */}
        <div
          className="
            w-full flex items-center gap-4 px-6 py-2
            font-mono text-[10px] uppercase tracking-[0.16em] text-paper-60
          "
        >
          <span
            className={hasAnyInFlight ? "phosphor-dot" : "phosphor-dot-idle"}
            aria-hidden
          />
          <span className="mr-1">BOARD</span>
          {(["running", "queued", "done", "failed"] as Phase[]).map((phase) => {
            const n = counts[phase];
            const isOpen = openPhase === phase;
            const disabled = n === 0 && !isOpen;
            return (
              <button
                key={phase}
                type="button"
                disabled={disabled}
                onClick={() =>
                  setOpenPhase((cur) => (cur === phase ? null : phase))
                }
                aria-expanded={isOpen}
                aria-controls={`board-phase-${phase}`}
                className={`
                  flex items-center gap-1 transition-colors
                  ${disabled ? "opacity-40 cursor-default" : "hover:text-paper cursor-pointer"}
                  ${isOpen ? "text-paper" : ""}
                `}
              >
                <span className={`tabular-nums ${PHASE_CLASS[phase]}`}>{n}</span>
                <span>{PHASE_LABEL[phase]}</span>
              </button>
            );
          })}
          <span className="ml-auto text-paper-40">
            {openPhase ? "▴ collapse" : items.length > 0 ? "▾ expand" : ""}
          </span>
        </div>

        {/* Expanded panel for the selected phase */}
        {openPhase && (
          <div
            id={`board-phase-${openPhase}`}
            className="px-6 pb-3 border-t border-paper-08/40"
          >
            {phaseGroups[openPhase].length === 0 ? (
              <p className="mt-2 font-mono text-[10px] uppercase tracking-wider text-paper-40">
                no {PHASE_LABEL[openPhase].toLowerCase()} tasks
              </p>
            ) : (
              <ul className="mt-2 space-y-3">
                {groupByAssignee(phaseGroups[openPhase]).map(
                  ([manager, tasks]) => (
                    <li key={manager}>
                      <div className="flex items-baseline gap-2 font-mono text-[10px] uppercase tracking-[0.16em] text-paper-60">
                        <span className={`tabular-nums ${PHASE_CLASS[openPhase]}`}>
                          {tasks.length}
                        </span>
                        <span className="text-paper">{manager}</span>
                      </div>
                      <ul className="ml-6 mt-1 space-y-[2px]">
                        {tasks.map((t) => (
                          <li
                            key={t.task_id}
                            className="flex items-center gap-2 font-mono text-[11px] text-paper-60"
                          >
                            <span
                              className={`${priorityClass(t.priority)} w-3 inline-block text-center`}
                              aria-hidden
                            >
                              {priorityGlyph(t.priority)}
                            </span>
                            <span className="truncate">{t.title}</span>
                            <span className="ml-auto text-paper-40 tabular-nums">
                              {fmtTime(t.lastEventTime)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </li>
                  ),
                )}
              </ul>
            )}
          </div>
        )}
      </div>
    );
  },
);

function priorityClass(p: BackgroundTaskItem["priority"]): string {
  if (p === "high") return "text-gold";
  if (p === "medium") return "text-signal-dim";
  return "text-paper-40";
}
