"use client";

/**
 * TaskCard component.
 * Renders a single board task with title, priority badge, assignee, and status indicator.
 */

import type { BoardTask, TaskPriority } from "@/types";

interface TaskCardProps {
  task: BoardTask;
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

export function TaskCard({ task }: TaskCardProps) {
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800 p-3 shadow-sm hover:border-indigo-500 transition-colors">
      {/* Title row */}
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

      {/* Footer row */}
      <div className="mt-2 flex items-center justify-between">
        {/* Assignee */}
        <span className="text-xs text-slate-400 truncate max-w-[120px]">
          {task.assignee || "Unassigned"}
        </span>

        {/* Status indicator */}
        <span
          className={`h-2.5 w-2.5 rounded-full ${statusDotClass[task.status]}`}
          title={task.status}
          aria-label={`Status: ${task.status}`}
        />
      </div>
    </div>
  );
}
