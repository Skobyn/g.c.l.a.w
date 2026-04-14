"use client";

/**
 * NewTaskModal — modal for creating a board task.
 *
 * Fields: title, description, assignee (from /admin/agents),
 * priority chips, initial column toggle, requires-approval toggle.
 */

import { useEffect, useState } from "react";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";
import type { AgentInfo, BoardTask, TaskPriority } from "@/types";

interface NewTaskModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (task: BoardTask) => void;
}

const PRIORITIES: TaskPriority[] = ["high", "medium", "low"];

export function NewTaskModal({ open, onClose, onCreated }: NewTaskModalProps) {
  const { getIdToken } = useAuth();

  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [assignee, setAssignee] = useState("");
  const [priority, setPriority] = useState<TaskPriority>("medium");
  const [initialStatus, setInitialStatus] = useState<"backlog" | "queued">(
    "queued",
  );
  const [requiresApproval, setRequiresApproval] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset on open
  useEffect(() => {
    if (!open) return;
    setTitle("");
    setDescription("");
    setPriority("medium");
    setInitialStatus("queued");
    setRequiresApproval(false);
    setError(null);
  }, [open]);

  // Load agents once when opened.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const api = createApiClient(getIdToken);
    setAgentsLoading(true);
    api
      .getAgents()
      .then((list) => {
        if (cancelled) return;
        setAgents(list);
        setAssignee((cur) => cur || list[0]?.name || "");
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load agents");
      })
      .finally(() => {
        if (!cancelled) setAgentsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, getIdToken]);

  // Close on Escape.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  const canSubmit = title.trim().length > 0 && assignee.length > 0 && !submitting;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const api = createApiClient(getIdToken);
      const task = await api.createBoardTask({
        title: title.trim(),
        description: description.trim() || undefined,
        assignee,
        priority,
        initial_status: initialStatus,
        requires_approval: requiresApproval,
      });
      onCreated(task);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create task");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-label="New task"
    >
      <div
        className="absolute inset-0 bg-black/60"
        onClick={onClose}
        aria-hidden="true"
      />
      <form
        onSubmit={handleSubmit}
        className="relative w-full max-w-lg rounded-xl border border-slate-700 bg-slate-900 shadow-2xl"
      >
        <header className="flex items-center justify-between border-b border-slate-700 px-5 py-4">
          <h2 className="text-base font-semibold text-slate-100">New Task</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-md p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
          >
            <svg
              className="h-5 w-5"
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
        </header>

        <div className="space-y-4 p-5">
          {error && (
            <div className="rounded-md border border-red-700 bg-red-950/40 px-3 py-2 text-sm text-red-300">
              {error}
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Title <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              autoFocus
              className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
              placeholder="Short, action-oriented title"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
              placeholder="Optional context for the agent"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Assignee <span className="text-red-400">*</span>
            </label>
            <select
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
              required
              disabled={agentsLoading}
              className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
            >
              {agentsLoading && <option value="">Loading agents…</option>}
              {!agentsLoading && agents.length === 0 && (
                <option value="">No agents available</option>
              )}
              {agents.map((a) => (
                <option key={a.name} value={a.name}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Priority
            </label>
            <div className="flex gap-2">
              {PRIORITIES.map((p) => {
                const active = priority === p;
                return (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setPriority(p)}
                    className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide border transition-colors ${
                      active
                        ? p === "high"
                          ? "bg-red-900 text-red-200 border-red-600"
                          : p === "medium"
                            ? "bg-yellow-900 text-yellow-200 border-yellow-600"
                            : "bg-green-900 text-green-200 border-green-600"
                        : "bg-slate-800 text-slate-400 border-slate-700 hover:border-slate-500"
                    }`}
                  >
                    {p}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Initial column
            </label>
            <div className="inline-flex rounded-md border border-slate-700 overflow-hidden">
              {(["backlog", "queued"] as const).map((s) => {
                const active = initialStatus === s;
                return (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setInitialStatus(s)}
                    className={`px-4 py-1.5 text-xs font-medium capitalize transition-colors ${
                      active
                        ? "bg-indigo-700 text-white"
                        : "bg-slate-800 text-slate-300 hover:bg-slate-700"
                    }`}
                  >
                    {s}
                  </button>
                );
              })}
            </div>
          </div>

          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={requiresApproval}
              onChange={(e) => setRequiresApproval(e.target.checked)}
              className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-indigo-600"
            />
            <span className="text-sm text-slate-300">
              Requires approval before execution
            </span>
          </label>
        </div>

        <footer className="flex items-center justify-end gap-2 border-t border-slate-700 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-600 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-800 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? "Creating…" : "Create Task"}
          </button>
        </footer>
      </form>
    </div>
  );
}
