"use client";

/**
 * BoardColumn component.
 *
 * Renders a kanban column with:
 *   - sticky header (label + count)
 *   - draggable TaskCards
 *   - HTML5 drop target that signals validity based on the currently
 *     dragged task's `fromStatus` and USER_ALLOWED_TRANSITIONS.
 *
 * Valid drop targets pulse a green ring; invalid ones flash a faint red
 * outline + cursor:not-allowed and reject the drop.
 */

import { useState } from "react";
import type {
  BoardTask,
  BoardColumn as BoardColumnType,
  TaskStatus,
} from "@/types";
import { USER_ALLOWED_TRANSITIONS } from "@/types";
import { TaskCard, type DragInfo } from "./task-card";

interface BoardColumnProps {
  column: BoardColumnType;
  tasks: BoardTask[];
  draggedTask: DragInfo | null;
  onDragStart: (info: DragInfo) => void;
  onDragEnd: () => void;
  onDrop: (info: DragInfo, target: TaskStatus) => void;
  onApprove?: (task: BoardTask) => Promise<void> | void;
  onReject?: (task: BoardTask, note: string) => Promise<void> | void;
}

export function BoardColumn({
  column,
  tasks,
  draggedTask,
  onDragStart,
  onDragEnd,
  onDrop,
  onApprove,
  onReject,
}: BoardColumnProps) {
  const [hovering, setHovering] = useState(false);
  const [invalidPulse, setInvalidPulse] = useState(false);

  const dragValidity: "none" | "valid" | "invalid" = (() => {
    if (!draggedTask) return "none";
    if (draggedTask.fromStatus === column.status) return "none";
    const allowed = USER_ALLOWED_TRANSITIONS[draggedTask.fromStatus] || [];
    return allowed.includes(column.status) ? "valid" : "invalid";
  })();

  const handleDragOver = (e: React.DragEvent) => {
    if (!draggedTask) return;
    if (dragValidity === "valid") {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      if (!hovering) setHovering(true);
    } else if (dragValidity === "invalid") {
      e.dataTransfer.dropEffect = "none";
      // Don't preventDefault → drop disallowed
    }
  };

  const handleDragLeave = () => {
    setHovering(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setHovering(false);
    if (!draggedTask) return;
    if (dragValidity !== "valid") {
      setInvalidPulse(true);
      setTimeout(() => setInvalidPulse(false), 400);
      return;
    }
    onDrop(draggedTask, column.status);
  };

  // Provide an "invalid" hint when hovering an invalid target.
  const handleDragEnter = (e: React.DragEvent) => {
    if (dragValidity === "invalid") {
      e.dataTransfer.dropEffect = "none";
      setInvalidPulse(true);
    }
  };

  const ringClass =
    dragValidity === "valid" && hovering
      ? "ring-2 ring-green-500"
      : dragValidity === "invalid" && invalidPulse
        ? "ring-2 ring-red-500/60"
        : "";

  const cursorClass = dragValidity === "invalid" ? "cursor-not-allowed" : "";

  return (
    <div
      className={`flex w-64 shrink-0 flex-col rounded-xl border border-slate-700 bg-slate-900 transition-shadow ${ringClass} ${cursorClass}`}
      onDragOver={handleDragOver}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
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

      <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-2">
        {tasks.length === 0 ? (
          <p className="py-4 text-center text-xs text-slate-500">No tasks</p>
        ) : (
          tasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              onDragStart={onDragStart}
              onDragEnd={onDragEnd}
              isDragging={draggedTask?.id === task.id}
              onApprove={onApprove}
              onReject={onReject}
            />
          ))
        )}
      </div>
    </div>
  );
}
