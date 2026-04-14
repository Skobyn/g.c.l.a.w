"use client";

/**
 * TaskCard component.
 *
 * Renders a single board task. Two visual modes:
 *   - Compact (default): for backlog/queued/in_progress/done columns.
 *   - Approval panel: when status === "needs_approval", shows full description
 *     and Approve/Reject buttons.
 *
 * Cards are draggable when their current status has at least one allowed
 * user-driven transition (see USER_ALLOWED_TRANSITIONS in @/types).
 */

import { useState } from "react";
import type { BoardTask, TaskPriority, TaskStatus } from "@/types";
import { USER_ALLOWED_TRANSITIONS } from "@/types";

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
}

const priorityBadgeClass: Record<TaskPriority, string> = {
  high: "bg-red-900 text-red-300 border border-red-700",
  medium: "bg-yellow-900 text-yellow-300 border border-yellow-700",
  low: "bg-green-900 text-green-300 border border-green-700",
};

const statusDotClass: Record<BoardTask["status"], string> = {
  backlog: "bg-gray-400",
  queued: "bg-blue-400",
  in_progress: "bg-yellow-400",
  needs_approval: "bg-orange-400",
  done: "bg-green-400",
  failed: "bg-red-400",
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
  if (hrs < 24) return `${hrs}h ${mins - hrs * 60}m`;
  const days = Math.floor(hrs / 24);
  return `${days}d ${hrs - days * 24}h`;
}

export function TaskCard({
  task,
  onDragStart,
  onDragEnd,
  isDragging,
  onApprove,
  onReject,
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

  const baseClass = `rounded-lg border bg-slate-800 p-3 shadow-sm transition-all ${
    draggable ? "cursor-grab active:cursor-grabbing" : "cursor-default"
  } ${
    isDragging
      ? "opacity-40 ring-2 ring-indigo-500"
      : "border-slate-700 hover:border-indigo-500"
  }`;

  if (task.status === "needs_approval") {
    return (
      <NeedsApprovalCard
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

  return (
    <div
      draggable={draggable}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      className={baseClass}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-slate-100 leading-snug line-clamp-2">
          {task.title}
        </p>
        <span
          className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${priorityBadgeClass[task.priority]}`}
        >
          {task.priority}
        </span>
      </div>

      {task.status === "failed" && task.rejection_note && (
        <p className="mt-2 text-xs text-slate-400 italic line-clamp-3">
          rejected: {task.rejection_note}
        </p>
      )}

      <div className="mt-2 flex items-center justify-between">
        <span className="text-xs text-slate-400 truncate max-w-[120px]">
          {task.assignee || "Unassigned"}
        </span>
        <span
          className={`h-2.5 w-2.5 rounded-full ${statusDotClass[task.status]}`}
          title={task.status}
          aria-label={`Status: ${task.status}`}
        />
      </div>
    </div>
  );
}

interface NeedsApprovalCardProps {
  task: BoardTask;
  draggable: boolean;
  isDragging: boolean;
  onDragStart: (e: React.DragEvent) => void;
  onDragEnd: () => void;
  onApprove?: (task: BoardTask) => Promise<void> | void;
  onReject?: (task: BoardTask, note: string) => Promise<void> | void;
}

function NeedsApprovalCard({
  task,
  draggable,
  isDragging,
  onDragStart,
  onDragEnd,
  onApprove,
  onReject,
}: NeedsApprovalCardProps) {
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const age = ageString(task.updated_at || task.created_at);

  const baseClass = `rounded-lg border bg-slate-800 shadow-sm transition-all ${
    draggable ? "cursor-grab active:cursor-grabbing" : "cursor-default"
  } ${
    isDragging
      ? "opacity-40 ring-2 ring-indigo-500"
      : "border-orange-700 hover:border-orange-500"
  }`;

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
    <div
      draggable={draggable}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      className={baseClass}
    >
      {/* Stripe */}
      <div className="flex items-center justify-between rounded-t-lg bg-orange-900/40 border-b border-orange-700 px-3 py-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-orange-200">
          Awaiting approval
        </span>
        {age && (
          <span className="text-[10px] text-orange-200/80">waiting {age}</span>
        )}
      </div>

      <div className="p-3">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-medium text-slate-100 leading-snug">
            {task.title}
          </p>
          <span
            className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${priorityBadgeClass[task.priority]}`}
          >
            {task.priority}
          </span>
        </div>

        {task.description && (
          <p className="mt-2 whitespace-pre-wrap text-xs text-slate-300 leading-relaxed">
            {task.description}
          </p>
        )}

        <div className="mt-2 flex items-center text-xs text-slate-400">
          <span className="truncate max-w-[160px]">
            {task.assignee || "Unassigned"}
          </span>
        </div>

        {error && (
          <p className="mt-2 text-xs text-red-400">{error}</p>
        )}

        {!rejecting ? (
          <div className="mt-3 flex gap-1.5">
            <button
              type="button"
              onClick={handleApprove}
              disabled={busy !== null}
              className="flex-1 rounded-md bg-green-700 px-2 py-1.5 text-xs font-semibold text-white hover:bg-green-600 disabled:opacity-50 transition-colors"
            >
              {busy === "approve" ? "Approving…" : "Approve"}
            </button>
            <button
              type="button"
              onClick={() => setRejecting(true)}
              disabled={busy !== null}
              className="flex-1 rounded-md bg-red-700 px-2 py-1.5 text-xs font-semibold text-white hover:bg-red-600 disabled:opacity-50 transition-colors"
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
              className="w-full rounded-md border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
            />
            <div className="flex gap-1.5">
              <button
                type="button"
                onClick={handleReject}
                disabled={busy !== null || note.trim().length === 0}
                className="flex-1 rounded-md bg-red-700 px-2 py-1.5 text-xs font-semibold text-white hover:bg-red-600 disabled:opacity-50 transition-colors"
              >
                {busy === "reject" ? "Rejecting…" : "Confirm Reject"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setRejecting(false);
                  setNote("");
                  setError(null);
                }}
                disabled={busy !== null}
                className="rounded-md border border-slate-600 px-2 py-1.5 text-xs text-slate-300 hover:bg-slate-800 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
