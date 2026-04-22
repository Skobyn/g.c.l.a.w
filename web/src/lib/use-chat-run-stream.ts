"use client";

/**
 * useChatRunStream — subscribe to /api/runs/{run_id}/events SSE and
 * fold board-task lifecycle events into a map of DispatchBlocks keyed
 * by task_id. Intended to be attached to a single assistant message
 * (the one whose `run_id` matches).
 *
 * Auto-disconnects when the run is "final" (either sees a terminal
 * orchestrator span or after `idleTimeoutMs` of no events post-message).
 */

import { useEffect, useRef, useState } from "react";
import type { DispatchBlock, DispatchSubEvent, TaskPriority } from "@/types";

interface Options {
  runId: string | undefined;
  /** Backend base URL (same as api-client's). */
  baseUrl: string;
  /** Bearer token getter for auth (same as api-client's). */
  getIdToken: () => Promise<string | null>;
  /** Disconnect if no events arrive for this long after connect. */
  idleTimeoutMs?: number;
}

export function useChatRunStream({
  runId,
  baseUrl,
  getIdToken,
  idleTimeoutMs = 45_000,
}: Options): Record<string, DispatchBlock> {
  const [blocks, setBlocks] = useState<Record<string, DispatchBlock>>({});
  const esRef = useRef<EventSource | null>(null);
  const seenEventIds = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!runId) return;

    // Reset dispatch state when run_id changes.
    setBlocks({});
    seenEventIds.current = new Set();

    let cancelled = false;
    let idleTimer: ReturnType<typeof setTimeout> | null = null;

    const resetIdle = () => {
      if (idleTimer) clearTimeout(idleTimer);
      idleTimer = setTimeout(() => {
        esRef.current?.close();
        esRef.current = null;
      }, idleTimeoutMs);
    };

    // EventSource doesn't support custom headers — Firebase ID token
    // needs to land as a query param. Skip auth entirely if dev bypass.
    (async () => {
      if (cancelled) return;
      const token = await getIdToken();
      const url = new URL(
        `${baseUrl}/api/runs/${encodeURIComponent(runId)}/events`,
      );
      if (token) url.searchParams.set("auth", token);
      const es = new EventSource(url.toString());
      esRef.current = es;
      resetIdle();

      es.onerror = () => {
        // Built-in reconnection will retry; don't tear down here.
      };

      // The backend emits SSE messages with `event: span.end` for OTel
      // spans and `event: task.*` for board events. Use a single
      // message listener that inspects the event payload shape.
      const onMessage = (raw: MessageEvent) => {
        resetIdle();
        try {
          const msg = JSON.parse(raw.data);
          applyEvent(msg, setBlocks, seenEventIds.current);
        } catch {
          // Ignore malformed lines — SSE can occasionally emit empty heartbeats.
        }
      };
      es.addEventListener("task.created", onMessage);
      es.addEventListener("task.picked_up", onMessage);
      es.addEventListener("task.completed", onMessage);
      es.addEventListener("task.failed", onMessage);
      // Fallback — some SSE servers send `data:` without a custom event name.
      es.onmessage = onMessage;
    })();

    return () => {
      cancelled = true;
      if (idleTimer) clearTimeout(idleTimer);
      esRef.current?.close();
      esRef.current = null;
    };
  }, [runId, baseUrl, getIdToken, idleTimeoutMs]);

  return blocks;
}

/** Fold one event into the dispatch map. Dedupes by a synthesized event id. */
function applyEvent(
  payload: { event?: string; data?: Record<string, unknown> },
  setBlocks: (
    fn: (prev: Record<string, DispatchBlock>) => Record<string, DispatchBlock>,
  ) => void,
  seen: Set<string>,
): void {
  const kind = String(payload.event ?? "");
  const data = (payload.data ?? {}) as Record<string, string>;
  const taskId = data.task_id;
  if (!taskId) return;

  const eventId = `${kind}:${taskId}:${data.time || ""}`;
  if (seen.has(eventId)) return;
  seen.add(eventId);

  setBlocks((prev) => {
    const next = { ...prev };
    const existing = next[taskId];
    const now = data.time || new Date().toISOString();

    if (kind === "task.created") {
      if (!existing) {
        next[taskId] = {
          task_id: taskId,
          title: data.title || "",
          priority: ((data.priority || "medium") as string).toLowerCase() as TaskPriority,
          assignee: data.assignee || "",
          created_at: now,
          events: [],
          status: "queued",
        };
      }
      return next;
    }

    if (!existing) return next; // event for a task we haven't seen created

    const sub: DispatchSubEvent = {
      id: eventId,
      time: now,
      agent: data.assignee || existing.assignee,
      kind: kind === "task.picked_up"
        ? "picked_up"
        : kind === "task.completed"
          ? "completed"
          : kind === "task.failed"
            ? "failed"
            : "info",
      text:
        kind === "task.picked_up"
          ? "started"
          : kind === "task.completed"
            ? (data.summary || "complete")
            : kind === "task.failed"
              ? (data.reason || "failed")
              : String(kind),
    };

    const updated: DispatchBlock = { ...existing };
    if (kind === "task.picked_up") updated.status = "in_progress";
    if (kind === "task.completed") {
      updated.status = "completed";
      updated.summary = data.summary;
    }
    if (kind === "task.failed") {
      updated.status = "failed";
      updated.reason = data.reason;
    }
    updated.events = [...updated.events, sub];
    next[taskId] = updated;
    return next;
  });
}
