"use client";

/**
 * BoardColumn component.
 * Renders a kanban column with a header (column label + task count) and a list of TaskCards.
 */

import type { BoardTask, BoardColumn as BoardColumnType } from "@/types";
import { TaskCard } from "./task-card";

interface BoardColumnProps {
  column: BoardColumnType;
  tasks: BoardTask[];
}

export function BoardColumn({ column, tasks }: BoardColumnProps) {
  return (
    <div className="flex w-64 shrink-0 flex-col rounded-xl border border-slate-700 bg-slate-900">
      {/* Column header */}
      <div
        className={`sticky top-0 z-10 flex items-center justify-between rounded-t-xl border-b-2 ${column.color} bg-slate-800 px-3 py-2`}
      >
        <span className="text-sm font-semibold text-slate-200">
          {column.label}
        </span>
        <span className="rounded-full bg-slate-700 px-2 py-0.5 text-xs font-medium text-slate-300">
          {tasks.length}
        </span>
      </div>

      {/* Task list */}
      <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-2">
        {tasks.length === 0 ? (
          <p className="py-4 text-center text-xs text-slate-500">No tasks</p>
        ) : (
          tasks.map((task) => <TaskCard key={task.id} task={task} />)
        )}
      </div>
    </div>
  );
}
