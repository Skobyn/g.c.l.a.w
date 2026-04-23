"use client";

/**
 * TaskCard — a typeset board entry.
 *
 * No enclosing box. Each task is 2–3 lines separated by a thin hairline
 * below. Title in Instrument Sans semibold, then a mono meta line, then
 * (optional) one-line description. Approval cards get an amber gold rule
 * on the left and typeset Approve / Reject buttons.
 */

import { useState } from "react";
import type { BoardTask, TaskStatus } from "@/types";
import { USER_ALLOWED_TRANSITIONS } from "@/types";
import { formatShortStamp, priorityGlyph } from "@/lib/format";

export interface DragInfo {
  id: string;
  fromStatus: TaskStatus;
}

interface TaskCardProps {
  task: BoardTask;
  onDragStart?: (info: DragInfo) => void;
  onDragEnd?: () => void;
  isDragging?: boolean;
  onApprove?: (task: BoardTask) => Promise<void> | void;
  onReject?: (task: BoardTask, note: string) => Promise<void> | void;
  /** Click anywhere on the card body → open the details modal. */
  onClick?: (task: BoardTask) => void;
}

const priorityColor: Record<string, string> = {
  H: "text-alert",
  M: "text-gold",
  L: "text-paper-40",
};

function ageString(iso: string | null | undefined): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const ms = Math.max(0, Date.now() - t);
  const mins = Math.floor(ms / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  const days = Math.floor(hrs / 24);
  return `${days}d`;
}

export function TaskCard({
  task,
  onDragStart,
  onDragEnd,
  isDragging,
  onApprove,
  onReject,
  onClick,
}: TaskCardProps) {
  const draggable = USER_ALLOWED_TRANSITIONS[task.status].length > 0;

  const handleDragStart = (e: React.DragEvent) => {
    if (!draggable) {
      e.preventDefault();
      return;
    }
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", task.id);
    e.dataTransfer.setData(
      "application/x-gclaw-task",
      JSON.stringify({ id: task.id, fromStatus: task.status }),
    );
    onDragStart?.({ id: task.id, fromStatus: task.status });
  };

  const handleDragEnd = () => {
    onDragEnd?.();
  };

  if (task.status === "needs_approval") {
    return (
      <NeedsApprovalEntry
        task={task}
        draggable={draggable}
        isDragging={!!isDragging}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onApprove={onApprove}
        onReject={onReject}
      />
    );
  }

  const glyph = priorityGlyph(task.priority);
  const priClass = priorityColor[glyph] ?? "text-paper-40";

  const clickable = !!onClick;

  return (
    <article
      draggable={draggable}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onClick={
        clickable
          ? (e) => {
              // Don't fire onClick while a drag is finishing.
              if (isDragging) return;
              e.stopPropagation();
              onClick?.(task);
            }
          : undefined
      }
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick?.(task);
              }
            }
          : undefined
      }
      className={`group py-3 px-3 -mx-1 hairline-b transition-colors ${
        draggable ? "cursor-grab active:cursor-grabbing" : clickable ? "cursor-pointer" : "cursor-default"
      } ${isDragging ? "opacity-40" : "hover:bg-ink-800"}`}
    >
      <p className="font-body text-[13.5px] font-medium text-paper leading-snug">
        {task.title}
      </p>
      <div className="mt-1.5 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.1em] text-paper-40">
        <span>{formatShortStamp(task.updated_at || task.created_at)}</span>
        <span>·</span>
        <span className="truncate max-w-[90px] text-paper-60">
          {task.assignee || "unassigned"}
        </span>
        <span className={`ml-auto font-bold ${priClass}`}>{glyph}</span>
      </div>
      {task.description && (
        <p className="mt-1 font-body text-[12px] text-paper-60 line-clamp-1 italic">
          {task.description}
        </p>
      )}
      {task.status === "failed" && task.rejection_note && (
        <p className="mt-1 font-mono text-[10px] text-alert line-clamp-2">
          rejected · {task.rejection_note}
        </p>
      )}
    </article>
  );
}

interface NeedsApprovalEntryProps {
  task: BoardTask;
  draggable: boolean;
  isDragging: boolean;
  onDragStart: (e: React.DragEvent) => void;
  onDragEnd: () => void;
  onApprove?: (task: BoardTask) => Promise<void> | void;
  onReject?: (task: BoardTask, note: string) => Promise<void> | void;
}

function NeedsApprovalEntry({
  task,
  draggable,
  isDragging,
  onDragStart,
  onDragEnd,
  onApprove,
  onReject,
}: NeedsApprovalEntryProps) {
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const age = ageString(task.updated_at || task.created_at);

  const handleApprove = async () => {
    if (!onApprove) return;
    setBusy("approve");
    setError(null);
    try {
      await onApprove(task);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approve failed");
      setBusy(null);
    }
  };

  const handleReject = async () => {
    if (!onReject) return;
    const trimmed = note.trim();
    if (!trimmed) {
      setError("Reason required");
      return;
    }
    setBusy("reject");
    setError(null);
    try {
      await onReject(task, trimmed);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reject failed");
      setBusy(null);
    }
  };

  return (
    <article
      draggable={draggable}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      className={`relative -mx-1 pl-3 pr-3 py-3 border-l-2 hairline-b transition-colors ${
        isDragging ? "opacity-40" : ""
      }`}
      style={{ borderLeftColor: "var(--gold)" }}
    >
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-gold font-semibold flex items-center gap-1.5">
          <span className="phosphor-dot-amber" />
          PENDING APPROVAL
        </span>
        {age && (
          <span className="font-mono text-[10px] text-paper-40 uppercase">
            · {age}
          </span>
        )}
      </div>

      <p className="mt-2 font-body text-[14px] font-medium text-paper leading-snug">
        {task.title}
      </p>

      {task.description && (
        <p className="mt-1 font-body text-[12px] text-paper-60 leading-relaxed line-clamp-3 whitespace-pre-wrap">
          {task.description}
        </p>
      )}

      <div className="mt-2 font-mono text-[10px] uppercase tracking-[0.1em] text-paper-40">
        ASSIGNEE · {task.assignee || "UNASSIGNED"}
      </div>

      {error && (
        <p className="mt-2 font-mono text-[10px] text-alert">{error}</p>
      )}

      {!rejecting ? (
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={handleApprove}
            disabled={busy !== null}
            className="btn-hair-signal flex-1"
          >
            {busy === "approve" ? "Approving…" : "Approve"}
          </button>
          <button
            type="button"
            onClick={() => setRejecting(true)}
            disabled={busy !== null}
            className="btn-hair-alert flex-1"
          >
            Reject
          </button>
        </div>
      ) : (
        <div className="mt-3 space-y-2">
          <textarea
            autoFocus
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            placeholder="Reason (required)"
            className="input-box font-body text-[12px]"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleReject}
              disabled={busy !== null || note.trim().length === 0}
              className="btn-hair-alert flex-1"
            >
              {busy === "reject" ? "Rejecting…" : "Confirm"}
            </button>
            <button
              type="button"
              onClick={() => {
                setRejecting(false);
                setNote("");
                setError(null);
              }}
              disabled={busy !== null}
              className="btn-hair"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
