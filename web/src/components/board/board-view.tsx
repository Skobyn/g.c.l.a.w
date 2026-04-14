"use client";

/**
 * BoardView — the unified kanban for GClaw.
 *
 * Columns, left to right:
 *   Scheduled | Backlog | Queued | In Progress | Needs Approval | Done | Failed
 *
 * Tasks are subscribed in real-time via Firestore onSnapshot on
 * `users/{uid}/board`. Crons are fetched via REST and polled every 10s
 * (they aren't mirrored to Firestore yet).
 *
 * Top bar exposes [+ New Task] and [+ New Cron].
 *
 * Drag-and-drop uses native HTML5 DnD (no libraries). The currently
 * dragged task lives in `draggedTask` state; columns highlight green when
 * the drop is allowed by USER_ALLOWED_TRANSITIONS, red when forbidden,
 * and the drop is rejected client-side. On allowed drop we call
 * `api.moveTaskStatus` with optimistic local update + rollback on error.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { collection, onSnapshot, query } from "firebase/firestore";
import { db, firebaseConfigured } from "@/lib/firebase";
import { useAuth } from "@/contexts/auth-context";
import { BOARD_COLUMNS } from "@/types";
import type { BoardTask, CronInfo, TaskStatus } from "@/types";
import { createApiClient } from "@/lib/api-client";
import { BoardColumn } from "./board-column";
import { ScheduledColumn } from "./scheduled-column";
import { CronEditDrawer } from "./cron-edit-drawer";
import { TaskCard, type DragInfo } from "./task-card";
import { NewTaskModal } from "./new-task-modal";
import { NewCronModal } from "./new-cron-modal";

const DONE_LIMIT = 20;
const CRON_POLL_MS = 10_000;

export function BoardView() {
  const { user, getIdToken } = useAuth();
  const [tasks, setTasks] = useState<BoardTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [crons, setCrons] = useState<CronInfo[]>([]);
  const [cronsLoading, setCronsLoading] = useState(true);
  const [cronsError, setCronsError] = useState<string | null>(null);

  const [editingCron, setEditingCron] = useState<CronInfo | null>(null);
  const [showAllDone, setShowAllDone] = useState(false);

  const [showNewTask, setShowNewTask] = useState(false);
  const [showNewCron, setShowNewCron] = useState(false);

  const [draggedTask, setDraggedTask] = useState<DragInfo | null>(null);

  // Refresh helper used after mutations (skipped when Firestore live).
  const refreshTasksRef = useRef<() => Promise<void>>(async () => {});

  // Task source: Firestore real-time when Firebase is configured,
  // REST polling every 10s otherwise.
  useEffect(() => {
    if (!user) return;

    if (firebaseConfigured) {
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
        },
      );
      refreshTasksRef.current = async () => {
        // Firestore is live — nothing to do.
      };
      return unsubscribe;
    }

    // REST polling fallback.
    let cancelled = false;
    const api = createApiClient(getIdToken);
    const load = async () => {
      try {
        const list = await api.getBoardTasks();
        if (!cancelled) {
          setTasks(list);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          console.error("getBoardTasks failed:", err);
          setError(
            err instanceof Error ? err.message : "Failed to load board tasks.",
          );
          setLoading(false);
        }
      }
    };
    refreshTasksRef.current = load;
    load();
    const handle = setInterval(load, 10_000);
    return () => {
      cancelled = true;
      clearInterval(handle);
    };
  }, [user, getIdToken]);

  // Cron polling (10s).
  const fetchCronsRef = useRef<() => Promise<void>>(async () => {});
  const fetchCrons = useCallback(async () => {
    try {
      const api = createApiClient(getIdToken);
      const list = await api.listCrons();
      setCrons(list);
      setCronsError(null);
    } catch (err) {
      setCronsError(err instanceof Error ? err.message : "Failed to load crons");
    } finally {
      setCronsLoading(false);
    }
  }, [getIdToken]);
  fetchCronsRef.current = fetchCrons;

  useEffect(() => {
    if (!user) return;
    fetchCrons();
    const handle = setInterval(() => {
      fetchCronsRef.current?.();
    }, CRON_POLL_MS);
    return () => clearInterval(handle);
  }, [user, fetchCrons]);

  // --- DnD handlers ---

  const handleDragStart = useCallback((info: DragInfo) => {
    setDraggedTask(info);
    setActionError(null);
  }, []);

  const handleDragEnd = useCallback(() => {
    setDraggedTask(null);
  }, []);

  const applyOptimistic = useCallback(
    (taskId: string, patch: Partial<BoardTask>) => {
      setTasks((prev) =>
        prev.map((t) => (t.id === taskId ? { ...t, ...patch } : t)),
      );
    },
    [],
  );

  const handleDrop = useCallback(
    async (info: DragInfo, target: TaskStatus) => {
      setDraggedTask(null);
      const original = tasks.find((t) => t.id === info.id);
      if (!original) return;
      // Optimistic
      applyOptimistic(info.id, { status: target });
      try {
        const api = createApiClient(getIdToken);
        const updated = await api.moveTaskStatus(info.id, target);
        applyOptimistic(info.id, updated);
        refreshTasksRef.current?.();
      } catch (err) {
        // Rollback
        applyOptimistic(info.id, { status: original.status });
        setActionError(
          err instanceof Error ? err.message : "Failed to move task",
        );
      }
    },
    [tasks, applyOptimistic, getIdToken],
  );

  // --- Approve / Reject ---

  const handleApprove = useCallback(
    async (task: BoardTask) => {
      const original = task.status;
      applyOptimistic(task.id, { status: "queued" });
      try {
        const api = createApiClient(getIdToken);
        const updated = await api.approveTask(task.id);
        applyOptimistic(task.id, updated);
        refreshTasksRef.current?.();
      } catch (err) {
        applyOptimistic(task.id, { status: original });
        setActionError(
          err instanceof Error ? err.message : "Failed to approve task",
        );
        throw err;
      }
    },
    [applyOptimistic, getIdToken],
  );

  const handleReject = useCallback(
    async (task: BoardTask, note: string) => {
      const original = task.status;
      applyOptimistic(task.id, { status: "failed", rejection_note: note });
      try {
        const api = createApiClient(getIdToken);
        const updated = await api.rejectTask(task.id, note);
        applyOptimistic(task.id, updated);
        refreshTasksRef.current?.();
      } catch (err) {
        applyOptimistic(task.id, { status: original, rejection_note: null });
        setActionError(
          err instanceof Error ? err.message : "Failed to reject task",
        );
        throw err;
      }
    },
    [applyOptimistic, getIdToken],
  );

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

  // Group tasks by status.
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

  tasksByStatus.done.sort((a, b) => {
    const ta = a.updated_at ? new Date(a.updated_at).getTime() : 0;
    const tb = b.updated_at ? new Date(b.updated_at).getTime() : 0;
    return tb - ta;
  });
  const doneTotal = tasksByStatus.done.length;
  const doneVisible = showAllDone
    ? tasksByStatus.done
    : tasksByStatus.done.slice(0, DONE_LIMIT);

  const handleCronSaved = (saved: CronInfo) => {
    setCrons((prev) => {
      const idx = prev.findIndex((c) => c.id === saved.id);
      if (idx === -1) return [saved, ...prev];
      const next = [...prev];
      next[idx] = saved;
      return next;
    });
  };

  const handleCronDeleted = (id: string) => {
    setCrons((prev) => prev.filter((c) => c.id !== id));
  };

  const handleTaskCreated = (task: BoardTask) => {
    setTasks((prev) =>
      prev.some((t) => t.id === task.id) ? prev : [task, ...prev],
    );
    refreshTasksRef.current?.();
  };

  return (
    <div className="flex h-full flex-col">
      {/* Top bar */}
      <div className="sticky top-0 z-20 flex items-center justify-between border-b border-slate-800 bg-slate-950 px-4 py-3">
        <h1 className="text-lg font-semibold text-slate-100">Board</h1>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowNewTask(true)}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 transition-colors"
          >
            + New Task
          </button>
          <button
            type="button"
            onClick={() => setShowNewCron(true)}
            className="rounded-md border border-purple-600 bg-purple-900/40 px-3 py-1.5 text-sm font-medium text-purple-200 hover:bg-purple-900/60 transition-colors"
          >
            + New Cron
          </button>
        </div>
      </div>

      {actionError && (
        <div className="mx-4 mt-3 flex items-center justify-between rounded-md border border-red-700 bg-red-950/40 px-3 py-2 text-sm text-red-300">
          <span>{actionError}</span>
          <button
            type="button"
            onClick={() => setActionError(null)}
            aria-label="Dismiss"
            className="ml-2 rounded p-0.5 text-red-300 hover:bg-red-900/40"
          >
            <svg
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>
      )}

      <div className="flex flex-1 gap-3 overflow-x-auto p-4">
        <ScheduledColumn
          crons={crons}
          loading={cronsLoading}
          error={cronsError}
          onCronClick={(c) => setEditingCron(c)}
        />

        {BOARD_COLUMNS.map((column) => {
          if (column.status === "done") {
            return (
              <DoneColumn
                key="done"
                column={column}
                visible={doneVisible}
                total={doneTotal}
                showAll={showAllDone}
                onShowAll={() => setShowAllDone(true)}
                draggedTask={draggedTask}
                onDragStart={handleDragStart}
                onDragEnd={handleDragEnd}
                onDrop={handleDrop}
              />
            );
          }
          return (
            <BoardColumn
              key={column.status}
              column={column}
              tasks={tasksByStatus[column.status]}
              draggedTask={draggedTask}
              onDragStart={handleDragStart}
              onDragEnd={handleDragEnd}
              onDrop={handleDrop}
              onApprove={handleApprove}
              onReject={handleReject}
            />
          );
        })}
      </div>

      <CronEditDrawer
        cron={editingCron}
        onClose={() => setEditingCron(null)}
        onSaved={handleCronSaved}
        onDeleted={handleCronDeleted}
      />

      <NewTaskModal
        open={showNewTask}
        onClose={() => setShowNewTask(false)}
        onCreated={handleTaskCreated}
      />

      <NewCronModal
        open={showNewCron}
        onClose={() => setShowNewCron(false)}
        onCreated={(c) => {
          handleCronSaved(c);
          fetchCronsRef.current?.();
        }}
      />
    </div>
  );
}

interface DoneColumnProps {
  column: (typeof BOARD_COLUMNS)[number];
  visible: BoardTask[];
  total: number;
  showAll: boolean;
  onShowAll: () => void;
  draggedTask: DragInfo | null;
  onDragStart: (info: DragInfo) => void;
  onDragEnd: () => void;
  onDrop: (info: DragInfo, target: TaskStatus) => void;
}

function DoneColumn({
  column,
  visible,
  total,
  showAll,
  onShowAll,
  draggedTask,
}: DoneColumnProps) {
  // Done is a terminal column — nothing transitions into it via user DnD,
  // and tasks in `done` aren't draggable. Render with no drop targets.
  return (
    <div className="flex w-64 shrink-0 flex-col rounded-xl border border-slate-700 bg-slate-900">
      <div
        className={`sticky top-0 z-10 flex items-center justify-between rounded-t-xl border-b-2 ${column.color} bg-slate-800 px-3 py-2`}
      >
        <span className="text-sm font-semibold text-slate-200">
          {column.label}
        </span>
        <span className="rounded-full bg-slate-700 px-2 py-0.5 text-xs font-medium text-slate-300">
          {total}
        </span>
      </div>
      <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-2">
        {visible.length === 0 ? (
          <p className="py-4 text-center text-xs text-slate-500">No tasks</p>
        ) : (
          <>
            {visible.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                isDragging={draggedTask?.id === task.id}
              />
            ))}
            {!showAll && total > visible.length && (
              <button
                type="button"
                onClick={onShowAll}
                className="mt-1 rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800 transition-colors"
              >
                Show all ({total})
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
