"use client";

/**
 * BoardView — editorial newspaper kanban.
 *
 * Header: § 01  BOARD, thin rule below. Columns are newspaper columns
 * separated by vertical hairlines (no surrounding boxes). Drag target
 * rules change color: green valid, orange forbidden.
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
import { TaskDetailsModal } from "./task-details-modal";
import { formatDatestamp } from "@/lib/format";

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
  const [activeTask, setActiveTask] = useState<BoardTask | null>(null);

  const refreshTasksRef = useRef<() => Promise<void>>(async () => {});

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
      refreshTasksRef.current = async () => {};
      return unsubscribe;
    }

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

  // Keep the open modal in sync with incoming board updates so
  // in-progress → done transitions show up live without a re-open.
  useEffect(() => {
    if (!activeTask) return;
    const fresh = tasks.find((t) => t.id === activeTask.id);
    if (fresh && fresh !== activeTask) {
      setActiveTask(fresh);
    }
  }, [tasks, activeTask]);

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
      applyOptimistic(info.id, { status: target });
      try {
        const api = createApiClient(getIdToken);
        const updated = await api.moveTaskStatus(info.id, target);
        applyOptimistic(info.id, updated);
        refreshTasksRef.current?.();
      } catch (err) {
        applyOptimistic(info.id, { status: original.status });
        setActionError(
          err instanceof Error ? err.message : "Failed to move task",
        );
      }
    },
    [tasks, applyOptimistic, getIdToken],
  );

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
        <p className="font-mono text-[11px] uppercase tracking-widest text-paper-40">
          LOADING BOARD<span className="signal-cursor" />
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="font-mono text-[11px] text-alert">{error}</p>
      </div>
    );
  }

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

  const pendingApproval = tasksByStatus.needs_approval.length;

  return (
    <div className="flex h-full flex-col bg-ink-900">
      {/* Page header */}
      <header className="hairline-b px-6 pt-6 pb-4">
        <div className="flex items-end justify-between gap-4">
          <div>
            <div className="label-caps mb-1.5">
              § 02 · WORK · {formatDatestamp(new Date(), { withDay: true, withTime: false })}
            </div>
            <h1 className="font-display text-[32px] leading-none italic">
              The Board
            </h1>
            <p className="mt-2 font-body text-[13px] text-paper-60">
              Seven columns. {tasks.length} in flight, {pendingApproval} awaiting
              your hand,{" "}
              <span className="text-gold">{crons.length} on the wire</span>.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowNewTask(true)}
              className="btn-hair-signal"
            >
              + Task
            </button>
            <button
              type="button"
              onClick={() => setShowNewCron(true)}
              className="btn-hair"
              style={{ borderColor: "var(--gold)", color: "var(--gold)" }}
            >
              + Cron
            </button>
          </div>
        </div>
      </header>

      {actionError && (
        <div className="mx-6 mt-4 border border-alert-dim bg-alert/5 px-3 py-2 flex items-center justify-between">
          <span className="font-mono text-[11px] uppercase tracking-wider text-alert">
            ERROR ·{" "}
            <span className="normal-case tracking-normal">{actionError}</span>
          </span>
          <button
            type="button"
            onClick={() => setActionError(null)}
            aria-label="Dismiss"
            className="font-mono text-[11px] text-alert hover:text-paper"
          >
            [X]
          </button>
        </div>
      )}

      {/* Columns */}
      <div className="flex flex-1 overflow-x-auto overflow-y-hidden gap-6 px-6 py-5 divide-x divide-paper-08">
        <div className="flex gap-6 min-w-max">
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
                  onTaskClick={setActiveTask}
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
                onTaskClick={setActiveTask}
              />
            );
          })}
        </div>
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

      <TaskDetailsModal
        task={activeTask}
        onClose={() => setActiveTask(null)}
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
  onTaskClick?: (task: BoardTask) => void;
}

function DoneColumn({
  column,
  visible,
  total,
  showAll,
  onShowAll,
  draggedTask,
  onTaskClick,
}: DoneColumnProps) {
  return (
    <div className="flex w-[260px] shrink-0 flex-col">
      <div className="pb-2 border-b-2 border-hair">
        <div className="flex items-baseline justify-between">
          <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-signal-dim">
            {column.label}
          </span>
          <span className="font-mono text-[10px] text-paper-40">
            ({total.toString().padStart(2, "0")})
          </span>
        </div>
      </div>
      <div className="flex flex-1 flex-col overflow-y-auto px-1">
        {visible.length === 0 ? (
          <p className="py-6 text-center font-mono text-[10px] uppercase tracking-widest text-paper-40">
            — empty —
          </p>
        ) : (
          <>
            {visible.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                isDragging={draggedTask?.id === task.id}
                onClick={onTaskClick}
              />
            ))}
            {!showAll && total > visible.length && (
              <button
                type="button"
                onClick={onShowAll}
                className="btn-hair my-3 self-start"
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
