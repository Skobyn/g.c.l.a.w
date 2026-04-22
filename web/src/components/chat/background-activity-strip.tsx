"use client";

/**
 * BackgroundActivityStrip — collapsible bar above the composer
 * showing board tasks picked up by a heartbeat-driven manager run
 * (i.e. events from runs outside the current chat session).
 *
 * Design ref: frontend-design spec §7 — sits between MessageList and
 * the input section's hairline-t, full transcript-width, phosphor-dot
 * at left with pulse when anything is in-flight.
 */

import { useState } from "react";
import type { TaskPriority } from "@/types";
import type { BackgroundTaskItem } from "@/lib/use-user-events";

interface Props {
  items: BackgroundTaskItem[];
  inFlight: number;
  queued: number;
}

function priorityGlyph(p: TaskPriority): string {
  if (p === "high") return "◐";
  if (p === "medium") return "◎";
  return "·";
}

function priorityClass(p: TaskPriority): string {
  if (p === "high") return "text-gold";
  if (p === "medium") return "text-signal-dim";
  return "text-paper-40";
}

function statusLabel(s: BackgroundTaskItem["status"]): string {
  if (s === "running") return "running";
  if (s === "queued") return "queued";
  if (s === "done") return "✓ done";
  if (s === "failed") return "✗ failed";
  return s;
}

function statusClass(s: BackgroundTaskItem["status"]): string {
  if (s === "running") return "text-signal-dim";
  if (s === "done") return "text-signal";
  if (s === "failed") return "text-alert";
  return "text-paper-40";
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

export function BackgroundActivityStrip({ items, inFlight, queued }: Props) {
  const [expanded, setExpanded] = useState(false);
  const hasAny = inFlight + queued > 0;
  const hasRenderable = items.length > 0;

  return (
    <div className="hairline-t bg-ink-900">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-3 px-6 py-2 font-mono text-[10px] uppercase tracking-[0.16em] text-left hover:bg-paper-08/30 transition-colors"
        aria-expanded={expanded}
        aria-controls="bg-activity-list"
      >
        <span className={hasAny ? "phosphor-dot" : "phosphor-dot-idle"} />
        <span className="text-paper-60">
          BACKGROUND ·{" "}
          <span className="text-signal-dim tabular-nums">{inFlight}</span>{" "}
          IN-FLIGHT ·{" "}
          <span className="tabular-nums">{queued}</span> QUEUED
          {!hasAny && " · IDLE"}
        </span>
        <span className="ml-auto text-paper-40">
          [ ↕ {expanded ? "COLLAPSE" : "EXPAND"} ]
        </span>
      </button>

      {expanded && hasRenderable && (
        <div
          id="bg-activity-list"
          className="hairline-t max-h-[220px] overflow-y-auto"
        >
          <ul className="px-6 py-2 space-y-[2px]">
            {items.map((t) => (
              <li
                key={t.task_id}
                className="flex items-baseline gap-3 font-mono text-[10px] py-0.5"
              >
                <span aria-hidden className={priorityClass(t.priority)}>
                  {priorityGlyph(t.priority)}
                </span>
                <span className="uppercase tracking-[0.14em] text-paper-60 w-16">
                  {t.priority}
                </span>
                <span className="text-paper-40">·</span>
                <button
                  type="button"
                  onClick={() =>
                    (window.location.href = `/board?task=${t.task_id}`)
                  }
                  className="text-paper-60 hover:text-paper w-20 text-left truncate"
                  title={t.title}
                >
                  {t.task_id}
                </button>
                <span className="text-paper-40">·</span>
                <span className="uppercase tracking-[0.14em] text-signal-dim w-28 truncate">
                  {t.manager}
                </span>
                <span className={`w-20 ${statusClass(t.status)}`}>
                  {t.status === "running" && (
                    <span className="signal-cursor mr-1" />
                  )}
                  {statusLabel(t.status)}
                </span>
                <span className="text-paper-40 ml-auto tabular-nums">
                  {fmtTime(t.lastEventTime)}
                </span>
                <button
                  type="button"
                  onClick={() =>
                    (window.location.href = `/board?task=${t.task_id}`)
                  }
                  className="text-paper-40 hover:text-signal ml-3"
                >
                  [ view ]
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {expanded && !hasRenderable && (
        <div className="hairline-t px-6 py-3 font-mono text-[10px] text-paper-40 italic">
          nothing in flight · heartbeat idle
        </div>
      )}
    </div>
  );
}
