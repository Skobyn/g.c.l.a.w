"use client";

/**
 * Form for creating a new cron job.
 * Calls the backend POST /admin/crons endpoint via ApiClient.
 */

import { useState } from "react";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";
import type { CronInfo } from "@/types";

interface CreateCronFormProps {
  onCreated: (cron: CronInfo) => void;
  onCancel: () => void;
}

interface FormState {
  title: string;
  description: string;
  schedule: string;
  mode: "auto" | "todo";
  assignee: string;
  task_priority: "high" | "medium" | "low";
}

const INITIAL_FORM: FormState = {
  title: "",
  description: "",
  schedule: "0 * * * *",
  mode: "auto",
  assignee: "",
  task_priority: "medium",
};

export function CreateCronForm({ onCreated, onCancel }: CreateCronFormProps) {
  const { getIdToken } = useAuth();
  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleChange(
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.title.trim() || !form.schedule.trim() || !form.assignee.trim()) {
      setError("Title, schedule, and assignee are required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const api = createApiClient(getIdToken);
      // ApiClient doesn't expose createCron yet — call raw via fetch fallback.
      // We reach into the api object to reuse its request helper via a cast.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const created: CronInfo = await (api as any).request("/admin/crons", {
        method: "POST",
        body: JSON.stringify(form),
      });
      onCreated(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create cron");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <div className="rounded-md border border-red-700 bg-red-900/30 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {/* Title */}
        <div className="sm:col-span-2">
          <label className="block text-xs font-medium text-slate-400 mb-1">Title *</label>
          <input
            type="text"
            name="title"
            value={form.title}
            onChange={handleChange}
            required
            placeholder="e.g. Daily digest"
            className="w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>

        {/* Description */}
        <div className="sm:col-span-2">
          <label className="block text-xs font-medium text-slate-400 mb-1">Description</label>
          <textarea
            name="description"
            value={form.description}
            onChange={handleChange}
            rows={2}
            placeholder="Optional description"
            className="w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>

        {/* Schedule */}
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">Schedule (cron) *</label>
          <input
            type="text"
            name="schedule"
            value={form.schedule}
            onChange={handleChange}
            required
            placeholder="0 * * * *"
            className="w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 font-mono text-sm text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>

        {/* Assignee */}
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">Assignee *</label>
          <input
            type="text"
            name="assignee"
            value={form.assignee}
            onChange={handleChange}
            required
            placeholder="e.g. main_agent"
            className="w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>

        {/* Mode */}
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">Mode</label>
          <select
            name="mode"
            value={form.mode}
            onChange={handleChange}
            className="w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="auto">Auto</option>
            <option value="todo">Todo</option>
          </select>
        </div>

        {/* Priority */}
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">Task Priority</label>
          <select
            name="task_priority"
            value={form.task_priority}
            onChange={handleChange}
            className="w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-end gap-3 pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-slate-600 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800 transition-colors"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors"
        >
          {submitting ? "Creating..." : "Create Cron"}
        </button>
      </div>
    </form>
  );
}
