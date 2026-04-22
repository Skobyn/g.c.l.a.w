"use client";

/**
 * DispatchBlock — inline board-task delegation + live execution log.
 *
 * Renders inside the orchestrator's assistant turn, after the prose body
 * and before the TOOLS footer. HIGH priority tasks show the full stream
 * with sub-events. MEDIUM / LOW render as a single "queued" bubble with
 * no follow-up in this thread.
 *
 * Design: "radio-operator's editorial notebook" — hairline-t separators,
 * mono labels, » glyphs, gold for HIGH, signal-dim for MEDIUM, paper-40
 * for LOW. See frontend-design spec for full rationale.
 */

import type { DispatchBlock as DispatchBlockT, TaskPriority } from "@/types";

interface Props {
  block: DispatchBlockT;
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

function managerClass(p: TaskPriority, status: DispatchBlockT["status"]): string {
  if (status === "failed") return "text-alert-dim";
  if (p === "high") return "text-signal";
  if (p === "medium") return "text-signal-dim";
  return "text-paper-60";
}

function fmtTime(iso: string): string {
  // Keep it compact: HH:MM:SS
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString(undefined, {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function DispatchBlockView({ block }: Props) {
  const isLow = block.priority === "low";
  const isMed = block.priority === "medium";
  const isQueuedOnly = (isMed || isLow) && block.status === "queued";

  const live = block.status === "in_progress";
  const failed = block.status === "failed";
  const done = block.status === "completed";

  // MEDIUM / LOW just-queued terse variant.
  if (isQueuedOnly) {
    return (
      <div className="mt-4 pt-3 hairline-t">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-paper-40">
          » QUEUED · {fmtTime(block.created_at)}
        </div>
        <div className="mt-1.5 flex items-baseline gap-2">
          <span aria-hidden className={priorityClass(block.priority)}>
            {priorityGlyph(block.priority)}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-paper-60">
            {block.priority}
          </span>
          <span className="text-paper-40">·</span>
          <button
            type="button"
            onClick={() =>
              (window.location.href = `/board?task=${block.task_id}`)
            }
            className="font-mono text-[10px] text-paper-60 hover:text-paper underline-offset-4 hover:underline"
            title={block.title}
          >
            {block.task_id}
          </button>
          <span className="text-paper-40">· →</span>
          <span
            className={`font-mono text-[10px] uppercase tracking-[0.14em] ${managerClass(
              block.priority,
              block.status,
            )}`}
          >
            {block.assignee}
          </span>
        </div>
        <p className="mt-1 pl-6 font-mono text-[10px] italic text-paper-40">
          will be processed on next heartbeat · no response expected inline
        </p>
      </div>
    );
  }

  // HIGH (or already-progressing MED/LOW — shouldn't happen in the
  // same chat turn but render it cleanly if it does) full stream.
  return (
    <div className="mt-4 pt-3 hairline-t">
      <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-paper-40">
        {live && <span className="phosphor-dot" />}
        {failed && <span className="phosphor-dot-alert" />}
        <span>» DISPATCH · {fmtTime(block.created_at)}</span>
      </div>

      <div className="mt-1.5 flex items-baseline gap-2 flex-wrap">
        <span aria-hidden className={priorityClass(block.priority)}>
          {priorityGlyph(block.priority)}
        </span>
        <span
          className={`font-mono text-[10px] uppercase tracking-[0.14em] ${priorityClass(
            block.priority,
          )}`}
        >
          {block.priority}
        </span>
        <span className="text-paper-40">·</span>
        <button
          type="button"
          onClick={() =>
            (window.location.href = `/board?task=${block.task_id}`)
          }
          className="font-mono text-[10px] text-paper-60 hover:text-paper underline-offset-4 hover:underline"
          title={block.title}
        >
          {block.task_id}
        </button>
        <span className="text-paper-40">· →</span>
        <span
          className={`font-mono text-[10px] uppercase tracking-[0.14em] ${managerClass(
            block.priority,
            block.status,
          )}`}
        >
          {block.assignee}
        </span>
        {live && <span className="signal-cursor" />}
      </div>

      {block.events.length > 0 && (
        <ul className="mt-1 pl-6 space-y-[2px]" aria-live="polite">
          {block.events.map((e, i) => (
            <li
              key={e.id}
              className="dispatch-event-enter flex items-baseline gap-2 font-mono text-[10.5px] leading-[1.55]"
              style={{ animationDelay: `${i * 30}ms` }}
            >
              <span className="text-paper-40 tabular-nums">· {fmtTime(e.time)}</span>
              {e.agent && <span className="text-signal">{e.agent}</span>}
              {e.kind === "completed" ? (
                <span className="text-signal dispatch-check-flash">
                  ✓ {e.text}
                </span>
              ) : e.kind === "failed" ? (
                <span className="text-alert">✗ {e.text}</span>
              ) : (
                <span className="text-paper-60">{e.text}</span>
              )}
              {live && i === block.events.length - 1 && !done && !failed && (
                <span className="signal-cursor" />
              )}
            </li>
          ))}
        </ul>
      )}

      {done && block.events.length === 0 && block.summary && (
        <p className="mt-1 pl-6 font-mono text-[10.5px] text-signal">
          <span className="dispatch-check-flash">✓ complete</span> — {block.summary}
        </p>
      )}

      {failed && block.reason && block.events.length === 0 && (
        <p className="mt-1 pl-6 font-mono text-[10.5px] text-alert">
          ✗ failed — {block.reason}
        </p>
      )}
    </div>
  );
}
