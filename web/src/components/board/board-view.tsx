"use client";

/**
 * BoardView component.
 * Connects to Firestore `users/{uid}/board` with a real-time onSnapshot listener.
 * Groups tasks by status and renders them in kanban columns using BOARD_COLUMNS.
 */

import { useEffect, useState } from "react";
import { collection, onSnapshot, query } from "firebase/firestore";
import { db } from "@/lib/firebase";
import { useAuth } from "@/contexts/auth-context";
import { BOARD_COLUMNS } from "@/types";
import type { BoardTask, TaskStatus } from "@/types";
import { BoardColumn } from "./board-column";

export function BoardView() {
  const { user } = useAuth();
  const [tasks, setTasks] = useState<BoardTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;

    const boardRef = collection(db, "users", user.uid, "board");
    const q = query(boardRef);

    const unsubscribe = onSnapshot(
      q,
      (snapshot) => {
        const fetched: BoardTask[] = snapshot.docs.map((doc) => ({
          id: doc.id,
          ...(doc.data() as Omit<BoardTask, "id">),
        }));
        setTasks(fetched);
        setLoading(false);
      },
      (err) => {
        console.error("Firestore onSnapshot error:", err);
        setError("Failed to load board tasks.");
        setLoading(false);
      }
    );

    return unsubscribe;
  }, [user]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm text-red-400">{error}</p>
      </div>
    );
  }

  // Group tasks by status
  const tasksByStatus: Record<TaskStatus, BoardTask[]> = {
    backlog: [],
    queued: [],
    in_progress: [],
    needs_approval: [],
    done: [],
    failed: [],
  };

  for (const task of tasks) {
    if (task.status in tasksByStatus) {
      tasksByStatus[task.status].push(task);
    }
  }

  return (
    <div className="flex h-full gap-3 overflow-x-auto p-4">
      {BOARD_COLUMNS.map((column) => (
        <BoardColumn
          key={column.status}
          column={column}
          tasks={tasksByStatus[column.status]}
        />
      ))}
    </div>
  );
}
