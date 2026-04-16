"use client";

/**
 * BoardColumn — newspaper column.
 *
 * No border around the column; vertical hairline separators do the work.
 * Header is small-caps mono with a count in parens. Drop-target state
 * toggles the header rule color (signal green valid, alert invalid).
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

  const handleDragEnter = (e: React.DragEvent) => {
    if (dragValidity === "invalid") {
      e.dataTransfer.dropEffect = "none";
      setInvalidPulse(true);
    }
  };

  const ruleColor =
    dragValidity === "valid" && hovering
      ? "border-signal"
      : dragValidity === "invalid" && invalidPulse
        ? "border-alert"
        : "border-hair";

  const cursorClass = dragValidity === "invalid" ? "cursor-not-allowed" : "";

  return (
    <div
      className={`flex w-[260px] shrink-0 flex-col ${cursorClass}`}
      onDragOver={handleDragOver}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className={`pb-2 border-b-2 transition-colors ${ruleColor}`}>
        <div className="flex items-baseline justify-between">
          <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-paper">
            {column.label}
          </span>
          <span className="font-mono text-[10px] text-paper-40">
            ({tasks.length.toString().padStart(2, "0")})
          </span>
        </div>
      </div>

      <div className="flex flex-1 flex-col overflow-y-auto px-1">
        {tasks.length === 0 ? (
          <p className="py-6 text-center font-mono text-[10px] uppercase tracking-widest text-paper-40">
            — empty —
          </p>
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
