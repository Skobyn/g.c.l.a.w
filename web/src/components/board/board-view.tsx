"use client";

/**
 * BoardView — the unified kanban for GClaw.
 *
 * Columns, left to right:
 *   Scheduled | Backlog | Queued | In Progress | Needs Approval | Done | Failed
 *
 * Tasks are subscribed in real-time via Firestore onSnapshot on
 * `users/{uid}/board`. Crons are fetched via REST and polled every 10s
 * (they aren't mirrored to Firestore yet). Clicking a cron card opens the
 * right-hand CronEditDrawer which reuses the CreateCronForm in edit mode.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { collection, onSnapshot, query } from "firebase/firestore";
import { db } from "@/lib/firebase";
import { useAuth } from "@/contexts/auth-context";
import { BOARD_COLUMNS } from "@/types";
import type { BoardTask, CronInfo, TaskStatus } from "@/types";
import { createApiClient } from "@/lib/api-client";
import { BoardColumn } from "./board-column";
import { ScheduledColumn } from "./scheduled-column";
import { CronEditDrawer } from "./cron-edit-drawer";
import { TaskCard } from "./task-card";

const DONE_LIMIT = 20;
const CRON_POLL_MS = 10_000;

export function BoardView() {
  const { user, getIdToken } = useAuth();
  const [tasks, setTasks] = useState<BoardTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [crons, setCrons] = useState<CronInfo[]>([]);
  const [cronsLoading, setCronsLoading] = useState(true);
  const [cronsError, setCronsError] = useState<string | null>(null);

  const [editingCron, setEditingCron] = useState<CronInfo | null>(null);
  const [showAllDone, setShowAllDone] = useState(false);

  // Firestore real-time task subscription.
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
      },
    );

    return unsubscribe;
  }, [user]);

  // Cron polling (10s). Uses listCrons which hits /crons.
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

  // Sort done by updated_at desc, then optionally trim.
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

  return (
    <>
      <div className="flex h-full gap-3 overflow-x-auto p-4">
        <ScheduledColumn
          crons={crons}
          loading={cronsLoading}
          error={cronsError}
          onCronClick={(c) => setEditingCron(c)}
        />

        {BOARD_COLUMNS.map((column) => {
          if (column.status === "done") {
            return (
              <div
                key="done"
                className="flex w-64 shrink-0 flex-col rounded-xl border border-slate-700 bg-slate-900"
              >
                <div
                  className={`sticky top-0 z-10 flex items-center justify-between rounded-t-xl border-b-2 ${column.color} bg-slate-800 px-3 py-2`}
                >
                  <span className="text-sm font-semibold text-slate-200">
                    {column.label}
                  </span>
                  <span className="rounded-full bg-slate-700 px-2 py-0.5 text-xs font-medium text-slate-300">
                    {doneTotal}
                  </span>
                </div>
                <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-2">
                  {doneVisible.length === 0 ? (
                    <p className="py-4 text-center text-xs text-slate-500">
                      No tasks
                    </p>
                  ) : (
                    <>
                      {doneVisible.map((task) => (
                        <DoneTaskCardWrapper key={task.id} task={task} />
                      ))}
                      {!showAllDone && doneTotal > DONE_LIMIT && (
                        <button
                          type="button"
                          onClick={() => setShowAllDone(true)}
                          className="mt-1 rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800 transition-colors"
                        >
                          Show all ({doneTotal})
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>
            );
          }
          return (
            <BoardColumn
              key={column.status}
              column={column}
              tasks={tasksByStatus[column.status]}
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
    </>
  );
}

function DoneTaskCardWrapper({ task }: { task: BoardTask }) {
  return <TaskCard task={task} />;
}
