"use client";

/**
 * useUserEvents — persistent SSE subscription to /api/events.
 *
 * Unlike useChatRunStream (which is session-scoped and ephemeral),
 * this hook stays open as long as the chat page is mounted and
 * collects every task.* event produced for the user — including
 * from heartbeat-driven manager runs the user isn't chatting in.
 *
 * Feeds the BackgroundActivityStrip.
 */

import { useEffect, useRef, useState } from "react";
import type { TaskPriority } from "@/types";

export interface BackgroundTaskItem {
  task_id: string;
  title: string;
  priority: TaskPriority;
  manager: string;
  status: "queued" | "running" | "done" | "failed";
  lastEventTime: string; // ISO
  summary?: string;
  reason?: string;
}

export interface UserEventsState {
  items: BackgroundTaskItem[];
  inFlight: number; // status === "running"
  queued: number;   // status === "queued"
}

interface Options {
  baseUrl: string;
  getIdToken: () => Promise<string | null>;
  /** Remove completed/failed items this long after they finish. */
  completedTtlMs?: number;
  /** Exclude items whose run_id matches this (avoid duplicating the
      inline-chat dispatch block). Optional. */
  excludeRunId?: string;
}

export function useUserEvents({
  baseUrl,
  getIdToken,
  completedTtlMs = 5 * 60_000,
}: Options): UserEventsState {
  const [items, setItems] = useState<BackgroundTaskItem[]>([]);
  const esRef = useRef<EventSource | null>(null);
  const seen = useRef<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;

    (async () => {
      if (cancelled) return;
      const token = await getIdToken();
      const url = new URL(`${baseUrl}/api/events`);
      if (token) url.searchParams.set("auth", token);
      const es = new EventSource(url.toString());
      esRef.current = es;

      const onMessage = (raw: MessageEvent) => {
        try {
          const msg = JSON.parse(raw.data);
          foldEvent(msg, setItems, seen.current);
        } catch {
          // ignore malformed
        }
      };
      es.addEventListener("task.created", onMessage);
      es.addEventListener("task.picked_up", onMessage);
      es.addEventListener("task.completed", onMessage);
      es.addEventListener("task.failed", onMessage);
      es.onmessage = onMessage;
      es.onerror = () => {
        // EventSource auto-reconnects; no-op.
      };
    })();

    return () => {
      cancelled = true;
      esRef.current?.close();
      esRef.current = null;
    };
  }, [baseUrl, getIdToken]);

  // TTL sweep for completed/failed items.
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      setItems((prev) =>
        prev.filter((it) => {
          if (it.status === "running" || it.status === "queued") return true;
          const t = Date.parse(it.lastEventTime);
          return isFinite(t) ? now - t < completedTtlMs : true;
        }),
      );
    }, 30_000);
    return () => clearInterval(interval);
  }, [completedTtlMs]);

  const inFlight = items.filter((i) => i.status === "running").length;
  const queued = items.filter((i) => i.status === "queued").length;
  return { items, inFlight, queued };
}

function foldEvent(
  payload: { event?: string; data?: Record<string, string> },
  setItems: (
    fn: (prev: BackgroundTaskItem[]) => BackgroundTaskItem[],
  ) => void,
  seenSet: Set<string>,
): void {
  const kind = String(payload.event ?? "");
  const data = (payload.data ?? {}) as Record<string, string>;
  const taskId = data.task_id;
  if (!taskId) return;

  const eventId = `${kind}:${taskId}:${data.time || ""}`;
  if (seenSet.has(eventId)) return;
  seenSet.add(eventId);

  const now = data.time || new Date().toISOString();

  setItems((prev) => {
    const idx = prev.findIndex((i) => i.task_id === taskId);
    if (kind === "task.created") {
      const item: BackgroundTaskItem = {
        task_id: taskId,
        title: data.title || "",
        priority: ((data.priority || "medium") as string).toLowerCase() as TaskPriority,
        manager: data.assignee || "",
        status: "queued",
        lastEventTime: now,
      };
      if (idx === -1) return [item, ...prev];
      const next = [...prev];
      next[idx] = { ...next[idx], ...item };
      return next;
    }
    if (idx === -1) return prev;
    const existing = prev[idx];
    const updated = { ...existing, lastEventTime: now };
    if (kind === "task.picked_up") updated.status = "running";
    if (kind === "task.completed") {
      updated.status = "done";
      updated.summary = data.summary;
    }
    if (kind === "task.failed") {
      updated.status = "failed";
      updated.reason = data.reason;
    }
    const next = [...prev];
    next[idx] = updated;
    return next;
  });
}
