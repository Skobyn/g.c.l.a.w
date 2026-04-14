"use client";

/**
 * Form for creating a new cron job.
 *
 * Sends the new structured shape to POST /crons:
 *   { title, description, assignee, schedule:{kind,...},
 *     payload:{kind,...}, delivery:{mode,...}, failure_alert?,
 *     wake_mode, enabled, delete_after_run, mode, task_priority }
 *
 * Backend also accepts the legacy flat shape; we always send the
 * structured one.
 */

import { useEffect, useMemo, useState } from "react";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";
import type {
  AgentInfo,
  CronInfo,
  DeliverySpec,
  FailureAlert,
  PayloadSpec,
  ScheduleSpec,
  TransportInfo,
} from "@/types";

interface CreateCronFormProps {
  onCreated?: (cron: CronInfo) => void;
  onSaved?: (cron: CronInfo) => void;
  onDeleted?: (cronId: string) => void;
  onCancel: () => void;
  /** When provided, the form runs in "edit" mode (PATCH instead of POST). */
  initial?: CronInfo;
}

type EveryUnit = "minutes" | "hours" | "days";
type ScheduleKind = "every" | "at" | "cron";
type PayloadKind = "agent_turn" | "system_event";
type DeliveryMode = "none" | "announce" | "webhook";

const UNIT_MS: Record<EveryUnit, number> = {
  minutes: 60_000,
  hours: 3_600_000,
  days: 86_400_000,
};

interface FormState {
  // Basic
  title: string;
  description: string;
  assignee: string;
  enabled: boolean;

  // Schedule
  scheduleKind: ScheduleKind;
  everyCount: number;
  everyUnit: EveryUnit;
  atISO: string; // datetime-local value
  cronExpr: string;
  cronTz: string;
  cronStaggerCount: number;
  cronStaggerUnit: EveryUnit;
  cronStaggerEnabled: boolean;

  // Execution
  wakeMode: "now" | "next-heartbeat";
  payloadKind: PayloadKind;
  agentMessage: string;
  agentModel: string;
  agentTimeoutSeconds: string;
  agentLightContext: boolean;
  mode: "auto" | "todo";
  task_priority: "high" | "medium" | "low";
  systemEventText: string;

  // Delivery
  deliveryMode: DeliveryMode;
  deliveryTransport: string;
  deliveryChannel: string;
  deliveryTo: string;
  deliveryAccountId: string;
  deliveryBestEffort: boolean;
  deliveryUrl: string;

  // Advanced
  deleteAfterRun: boolean;
  failureAlertEnabled: boolean;
  failureAfter: number;
  failureCooldownSeconds: number;
  failureChannel: string;
  failureTo: string;
  failureUrl: string;
  failureMode: "announce" | "webhook";
  failureTransport: string;
}

const INITIAL_FORM: FormState = {
  title: "",
  description: "",
  assignee: "",
  enabled: true,

  scheduleKind: "every",
  everyCount: 30,
  everyUnit: "minutes",
  atISO: "",
  cronExpr: "0 7 * * *",
  cronTz: "",
  cronStaggerCount: 0,
  cronStaggerUnit: "minutes",
  cronStaggerEnabled: false,

  wakeMode: "now",
  payloadKind: "agent_turn",
  agentMessage: "",
  agentModel: "",
  agentTimeoutSeconds: "",
  agentLightContext: false,
  mode: "auto",
  task_priority: "medium",
  systemEventText: "",

  deliveryMode: "none",
  deliveryTransport: "default",
  deliveryChannel: "",
  deliveryTo: "",
  deliveryAccountId: "",
  deliveryBestEffort: false,
  deliveryUrl: "",

  deleteAfterRun: false,
  failureAlertEnabled: false,
  failureAfter: 3,
  failureCooldownSeconds: 3600,
  failureChannel: "",
  failureTo: "",
  failureUrl: "",
  failureMode: "announce",
  failureTransport: "default",
};

const CRON_PRESETS: { label: string; expr: string }[] = [
  { label: "Hourly", expr: "0 * * * *" },
  { label: "Daily 8am", expr: "0 8 * * *" },
  { label: "Weekly Mon 9am", expr: "0 9 * * 1" },
  { label: "Every 15min", expr: "*/15 * * * *" },
];

// --- small presentational helpers --------------------------------------

function Section({
  title,
  children,
  defaultOpen = true,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details
      open={defaultOpen}
      className="group rounded-lg border border-slate-700 bg-slate-900/60"
    >
      <summary className="flex cursor-pointer items-center justify-between px-4 py-3 text-sm font-semibold text-slate-200 hover:bg-slate-800/60">
        <span>{title}</span>
        <svg
          className="h-4 w-4 text-slate-400 transition-transform group-open:rotate-180"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </summary>
      <div className="space-y-4 border-t border-slate-700 p-4">{children}</div>
    </details>
  );
}

const INPUT_CLS =
  "w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500";

const LABEL_CLS = "block text-xs font-medium text-slate-400 mb-1";

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 rounded border-slate-600 bg-slate-900 text-indigo-500 focus:ring-indigo-500"
      />
      <span>{label}</span>
    </label>
  );
}

// -----------------------------------------------------------------------

function formStateFromCron(cron: CronInfo): FormState {
  const s = cron.schedule;
  let scheduleKind: ScheduleKind = "every";
  let everyCount = INITIAL_FORM.everyCount;
  let everyUnit: EveryUnit = "minutes";
  let atISO = "";
  let cronExpr = INITIAL_FORM.cronExpr;
  let cronTz = "";
  let cronStaggerCount = 0;
  let cronStaggerUnit: EveryUnit = "minutes";
  let cronStaggerEnabled = false;

  if (s && typeof s === "object") {
    if (s.kind === "every") {
      scheduleKind = "every";
      const ms = s.every_ms;
      if (ms % UNIT_MS.days === 0) {
        everyCount = ms / UNIT_MS.days;
        everyUnit = "days";
      } else if (ms % UNIT_MS.hours === 0) {
        everyCount = ms / UNIT_MS.hours;
        everyUnit = "hours";
      } else {
        everyCount = Math.round(ms / UNIT_MS.minutes);
        everyUnit = "minutes";
      }
    } else if (s.kind === "at") {
      scheduleKind = "at";
      try {
        const d = new Date(s.at);
        const pad = (n: number) => String(n).padStart(2, "0");
        atISO = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
      } catch {
        atISO = "";
      }
    } else if (s.kind === "cron") {
      scheduleKind = "cron";
      cronExpr = s.expr;
      cronTz = s.tz ?? "";
      if (s.stagger_ms && s.stagger_ms > 0) {
        cronStaggerEnabled = true;
        const ms = s.stagger_ms;
        if (ms % UNIT_MS.days === 0) {
          cronStaggerCount = ms / UNIT_MS.days;
          cronStaggerUnit = "days";
        } else if (ms % UNIT_MS.hours === 0) {
          cronStaggerCount = ms / UNIT_MS.hours;
          cronStaggerUnit = "hours";
        } else {
          cronStaggerCount = Math.round(ms / UNIT_MS.minutes);
          cronStaggerUnit = "minutes";
        }
      }
    }
  }

  const p = cron.payload;
  let payloadKind: PayloadKind = "agent_turn";
  let agentMessage = "";
  let agentModel = "";
  let agentTimeoutSeconds = "";
  let agentLightContext = false;
  let systemEventText = "";
  if (p && p.kind === "agent_turn") {
    payloadKind = "agent_turn";
    agentMessage = p.message ?? "";
    agentModel = p.model ?? "";
    agentTimeoutSeconds =
      p.timeout_seconds != null ? String(p.timeout_seconds) : "";
    agentLightContext = !!p.light_context;
  } else if (p && p.kind === "system_event") {
    payloadKind = "system_event";
    systemEventText = p.text ?? "";
  }

  const d = cron.delivery;
  let deliveryMode: DeliveryMode = "none";
  let deliveryTransport = "default";
  let deliveryChannel = "";
  let deliveryTo = "";
  let deliveryAccountId = "";
  let deliveryBestEffort = false;
  let deliveryUrl = "";
  if (d && d.mode === "announce") {
    deliveryMode = "announce";
    deliveryTransport = d.transport ?? "default";
    deliveryChannel = d.channel ?? "";
    deliveryTo = d.to ?? "";
    deliveryAccountId = d.account_id ?? "";
    deliveryBestEffort = !!d.best_effort;
  } else if (d && d.mode === "webhook") {
    deliveryMode = "webhook";
    deliveryUrl = d.url ?? "";
    deliveryBestEffort = !!d.best_effort;
  }

  const fa = cron.failure_alert;
  const failureAlertEnabled = !!fa;
  const failureAfter = fa?.after ?? 3;
  const failureCooldownSeconds = fa
    ? Math.round((fa.cooldown_ms ?? 0) / 1000)
    : 3600;
  const failureMode: "announce" | "webhook" = fa?.mode ?? "announce";
  const failureTransport = fa?.transport ?? "default";
  const failureChannel = fa?.channel ?? "";
  const failureTo = fa?.to ?? "";
  const failureUrl = fa?.url ?? "";

  return {
    title: cron.title ?? "",
    description: cron.description ?? "",
    assignee: cron.assignee ?? "",
    enabled: cron.enabled,

    scheduleKind,
    everyCount,
    everyUnit,
    atISO,
    cronExpr,
    cronTz,
    cronStaggerCount,
    cronStaggerUnit,
    cronStaggerEnabled,

    wakeMode: cron.wake_mode,
    payloadKind,
    agentMessage,
    agentModel,
    agentTimeoutSeconds,
    agentLightContext,
    mode: cron.mode,
    task_priority: (["high", "medium", "low"].includes(
      cron.task_priority as string,
    )
      ? (cron.task_priority as "high" | "medium" | "low")
      : "medium"),
    systemEventText,

    deliveryMode,
    deliveryTransport,
    deliveryChannel,
    deliveryTo,
    deliveryAccountId,
    deliveryBestEffort,
    deliveryUrl,

    deleteAfterRun: cron.delete_after_run,
    failureAlertEnabled,
    failureAfter,
    failureCooldownSeconds,
    failureChannel,
    failureTo,
    failureUrl,
    failureMode,
    failureTransport,
  };
}

export function CreateCronForm({
  onCreated,
  onSaved,
  onDeleted,
  onCancel,
  initial,
}: CreateCronFormProps) {
  const { getIdToken } = useAuth();
  const isEdit = !!initial;
  const [form, setForm] = useState<FormState>(() =>
    initial ? formStateFromCron(initial) : INITIAL_FORM,
  );
  const [deleting, setDeleting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [agentsError, setAgentsError] = useState<string | null>(null);

  const [transports, setTransports] = useState<TransportInfo | null>(null);
  const [transportsError, setTransportsError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const api = createApiClient(getIdToken);
      try {
        const list = await api.getAgents();
        if (cancelled) return;
        setAgents(list);
        setForm((prev) =>
          prev.assignee || list.length === 0
            ? prev
            : { ...prev, assignee: list[0].name },
        );
      } catch (err) {
        if (!cancelled) {
          setAgentsError(
            err instanceof Error ? err.message : "Failed to load agents",
          );
        }
      } finally {
        if (!cancelled) setAgentsLoading(false);
      }

      try {
        const info = await api.getTransports();
        if (cancelled) return;
        setTransports(info);
      } catch (err) {
        if (!cancelled) {
          setTransportsError(
            err instanceof Error ? err.message : "Failed to load transports",
          );
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [getIdToken]);

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const buildSchedule = useMemo((): ScheduleSpec | { error: string } => {
    if (form.scheduleKind === "every") {
      const n = Number(form.everyCount);
      if (!Number.isFinite(n) || n <= 0)
        return { error: "Every interval must be > 0." };
      return { kind: "every", every_ms: Math.round(n * UNIT_MS[form.everyUnit]) };
    }
    if (form.scheduleKind === "at") {
      if (!form.atISO.trim())
        return { error: "Pick a date/time for 'at' schedule." };
      const d = new Date(form.atISO);
      if (Number.isNaN(d.getTime()))
        return { error: "Invalid date/time for 'at' schedule." };
      return { kind: "at", at: d.toISOString() };
    }
    // cron
    if (!form.cronExpr.trim())
      return { error: "Cron expression is required." };
    const spec: ScheduleSpec = { kind: "cron", expr: form.cronExpr.trim() };
    if (form.cronTz.trim()) spec.tz = form.cronTz.trim();
    if (form.cronStaggerEnabled) {
      const s = Number(form.cronStaggerCount);
      if (Number.isFinite(s) && s > 0) {
        spec.stagger_ms = Math.round(s * UNIT_MS[form.cronStaggerUnit]);
      }
    }
    return spec;
  }, [form]);

  const buildPayload = useMemo((): PayloadSpec | { error: string } => {
    if (form.payloadKind === "agent_turn") {
      if (!form.agentMessage.trim())
        return { error: "Agent message is required." };
      const p: PayloadSpec = {
        kind: "agent_turn",
        message: form.agentMessage,
        light_context: form.agentLightContext,
      };
      if (form.agentModel.trim()) p.model = form.agentModel.trim();
      if (form.agentTimeoutSeconds.trim()) {
        const t = Number(form.agentTimeoutSeconds);
        if (Number.isFinite(t) && t > 0) p.timeout_seconds = t;
      }
      return p;
    }
    if (!form.systemEventText.trim())
      return { error: "System event text is required." };
    return { kind: "system_event", text: form.systemEventText };
  }, [form]);

  const buildDelivery = (): DeliverySpec | { error: string } => {
    if (form.deliveryMode === "none") return { mode: "none" };
    if (form.deliveryMode === "webhook") {
      if (!form.deliveryUrl.trim())
        return { error: "Webhook URL is required." };
      return {
        mode: "webhook",
        url: form.deliveryUrl.trim(),
        best_effort: form.deliveryBestEffort,
      };
    }
    return {
      mode: "announce",
      transport: form.deliveryTransport || "default",
      channel: form.deliveryChannel.trim() || null,
      to: form.deliveryTo.trim() || null,
      account_id: form.deliveryAccountId.trim() || null,
      best_effort: form.deliveryBestEffort,
    };
  };

  const buildFailureAlert = (): FailureAlert | null => {
    if (!form.failureAlertEnabled) return null;
    const alert: FailureAlert = {
      after: Math.max(1, Number(form.failureAfter) || 1),
      cooldown_ms: Math.max(0, Number(form.failureCooldownSeconds) || 0) * 1000,
      mode: form.failureMode,
    };
    if (form.failureMode === "webhook") {
      if (form.failureUrl.trim()) alert.url = form.failureUrl.trim();
    } else {
      alert.transport = form.failureTransport || "default";
      if (form.failureChannel.trim()) alert.channel = form.failureChannel.trim();
      if (form.failureTo.trim()) alert.to = form.failureTo.trim();
    }
    return alert;
  };

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    if (!form.title.trim()) {
      setError("Name is required.");
      return;
    }
    if (!form.assignee.trim()) {
      setError("Agent is required.");
      return;
    }

    const schedule = buildSchedule;
    if ("error" in schedule) {
      setError(schedule.error);
      return;
    }
    const payload = buildPayload;
    if ("error" in payload) {
      setError(payload.error);
      return;
    }
    const delivery = buildDelivery();
    if ("error" in delivery) {
      setError(delivery.error);
      return;
    }

    const body = {
      title: form.title.trim(),
      description: form.description,
      assignee: form.assignee,
      enabled: form.enabled,
      schedule,
      payload,
      delivery,
      failure_alert: buildFailureAlert(),
      wake_mode: form.wakeMode,
      delete_after_run: form.deleteAfterRun,
      mode: form.mode,
      task_priority: form.task_priority,
    };

    setSubmitting(true);
    setError(null);
    try {
      const api = createApiClient(getIdToken);
      if (isEdit && initial) {
        const updated = await api.updateCron(
          initial.id,
          body as Partial<CronInfo>,
        );
        onSaved?.(updated);
      } else {
        const created = await api.post<CronInfo>("/crons", body);
        onCreated?.(created);
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : isEdit
          ? "Failed to save cron"
          : "Failed to create cron",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete() {
    if (!initial) return;
    if (
      typeof window !== "undefined" &&
      !window.confirm(`Delete cron "${initial.title}"? This cannot be undone.`)
    ) {
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      const api = createApiClient(getIdToken);
      await api.deleteCron(initial.id);
      onDeleted?.(initial.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete cron");
      setDeleting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <div className="rounded-md border border-red-700 bg-red-900/30 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* ----- Basic ----- */}
      <Section title="Basic" defaultOpen>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className={LABEL_CLS}>Name *</label>
            <input
              type="text"
              value={form.title}
              onChange={(e) => update("title", e.target.value)}
              required
              placeholder="e.g. Daily digest"
              className={INPUT_CLS}
            />
          </div>

          <div className="sm:col-span-2">
            <label className={LABEL_CLS}>Description</label>
            <textarea
              value={form.description}
              onChange={(e) => update("description", e.target.value)}
              rows={2}
              placeholder="Optional description"
              className={INPUT_CLS}
            />
          </div>

          <div>
            <label className={LABEL_CLS}>Agent *</label>
            <select
              value={form.assignee}
              onChange={(e) => update("assignee", e.target.value)}
              required
              disabled={agentsLoading}
              className={INPUT_CLS}
            >
              {agentsLoading && <option value="">Loading agents...</option>}
              {!agentsLoading && agents.length === 0 && (
                <option value="">(no agents available)</option>
              )}
              {!agentsLoading &&
                agents.map((a) => (
                  <option key={a.name} value={a.name}>
                    {a.name}
                    {a.has_soul_overlay ? "  (soul)" : ""}
                  </option>
                ))}
            </select>
            {agentsError && (
              <p className="mt-1 text-xs text-red-400">{agentsError}</p>
            )}
          </div>

          <div className="flex items-end">
            <Toggle
              checked={form.enabled}
              onChange={(v) => update("enabled", v)}
              label="Enabled"
            />
          </div>
        </div>
      </Section>

      {/* ----- Schedule ----- */}
      <Section title="Schedule" defaultOpen>
        <div className="flex flex-wrap gap-2">
          {(["every", "at", "cron"] as ScheduleKind[]).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => update("scheduleKind", k)}
              className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                form.scheduleKind === k
                  ? "border-indigo-500 bg-indigo-600/30 text-indigo-200"
                  : "border-slate-600 text-slate-300 hover:bg-slate-800"
              }`}
            >
              {k}
            </button>
          ))}
        </div>

        {form.scheduleKind === "every" && (
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className={LABEL_CLS}>Every</label>
              <input
                type="number"
                min={1}
                value={form.everyCount}
                onChange={(e) =>
                  update("everyCount", Number(e.target.value) || 0)
                }
                className={INPUT_CLS}
              />
            </div>
            <div>
              <label className={LABEL_CLS}>Unit</label>
              <select
                value={form.everyUnit}
                onChange={(e) =>
                  update("everyUnit", e.target.value as EveryUnit)
                }
                className={INPUT_CLS}
              >
                <option value="minutes">minutes</option>
                <option value="hours">hours</option>
                <option value="days">days</option>
              </select>
            </div>
          </div>
        )}

        {form.scheduleKind === "at" && (
          <div>
            <label className={LABEL_CLS}>Run at</label>
            <input
              type="datetime-local"
              value={form.atISO}
              onChange={(e) => update("atISO", e.target.value)}
              className={INPUT_CLS}
            />
          </div>
        )}

        {form.scheduleKind === "cron" && (
          <div className="space-y-3">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className={LABEL_CLS}>Cron expression *</label>
                <input
                  type="text"
                  value={form.cronExpr}
                  onChange={(e) => update("cronExpr", e.target.value)}
                  placeholder="0 7 * * *"
                  className={`${INPUT_CLS} font-mono`}
                />
              </div>
              <div>
                <label className={LABEL_CLS}>Timezone (optional)</label>
                <input
                  type="text"
                  value={form.cronTz}
                  onChange={(e) => update("cronTz", e.target.value)}
                  placeholder="America/New_York"
                  className={INPUT_CLS}
                />
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              {CRON_PRESETS.map((p) => (
                <button
                  key={p.label}
                  type="button"
                  onClick={() => update("cronExpr", p.expr)}
                  className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
                >
                  {p.label}
                </button>
              ))}
            </div>

            <div className="space-y-2">
              <Toggle
                checked={form.cronStaggerEnabled}
                onChange={(v) => update("cronStaggerEnabled", v)}
                label="Stagger (spread instances over a window)"
              />
              {form.cronStaggerEnabled && (
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className={LABEL_CLS}>Stagger amount</label>
                    <input
                      type="number"
                      min={0}
                      value={form.cronStaggerCount}
                      onChange={(e) =>
                        update("cronStaggerCount", Number(e.target.value) || 0)
                      }
                      className={INPUT_CLS}
                    />
                  </div>
                  <div>
                    <label className={LABEL_CLS}>Stagger unit</label>
                    <select
                      value={form.cronStaggerUnit}
                      onChange={(e) =>
                        update("cronStaggerUnit", e.target.value as EveryUnit)
                      }
                      className={INPUT_CLS}
                    >
                      <option value="minutes">minutes</option>
                      <option value="hours">hours</option>
                      <option value="days">days</option>
                    </select>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </Section>

      {/* ----- Execution ----- */}
      <Section title="Execution" defaultOpen>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className={LABEL_CLS}>Wake mode</label>
            <select
              value={form.wakeMode}
              onChange={(e) =>
                update("wakeMode", e.target.value as FormState["wakeMode"])
              }
              className={INPUT_CLS}
            >
              <option value="now">now</option>
              <option value="next-heartbeat">next-heartbeat</option>
            </select>
          </div>
          <div>
            <label className={LABEL_CLS}>Payload kind</label>
            <select
              value={form.payloadKind}
              onChange={(e) =>
                update("payloadKind", e.target.value as PayloadKind)
              }
              className={INPUT_CLS}
            >
              <option value="agent_turn">agent_turn</option>
              <option value="system_event">system_event</option>
            </select>
          </div>
        </div>

        {form.payloadKind === "agent_turn" && (
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className={LABEL_CLS}>Message *</label>
              <textarea
                value={form.agentMessage}
                onChange={(e) => update("agentMessage", e.target.value)}
                rows={3}
                placeholder="What should the agent do?"
                className={INPUT_CLS}
              />
            </div>
            <div>
              <label className={LABEL_CLS}>Model override (optional)</label>
              <input
                type="text"
                value={form.agentModel}
                onChange={(e) => update("agentModel", e.target.value)}
                placeholder="gemini-2.0-flash"
                className={INPUT_CLS}
              />
            </div>
            <div>
              <label className={LABEL_CLS}>Timeout (seconds, optional)</label>
              <input
                type="number"
                min={1}
                value={form.agentTimeoutSeconds}
                onChange={(e) =>
                  update("agentTimeoutSeconds", e.target.value)
                }
                className={INPUT_CLS}
              />
            </div>
            <div>
              <label className={LABEL_CLS}>Mode</label>
              <select
                value={form.mode}
                onChange={(e) =>
                  update("mode", e.target.value as FormState["mode"])
                }
                className={INPUT_CLS}
              >
                <option value="auto">auto</option>
                <option value="todo">todo</option>
              </select>
            </div>
            <div>
              <label className={LABEL_CLS}>Task priority</label>
              <select
                value={form.task_priority}
                onChange={(e) =>
                  update(
                    "task_priority",
                    e.target.value as FormState["task_priority"],
                  )
                }
                className={INPUT_CLS}
              >
                <option value="high">high</option>
                <option value="medium">medium</option>
                <option value="low">low</option>
              </select>
            </div>
            <div className="sm:col-span-2">
              <Toggle
                checked={form.agentLightContext}
                onChange={(v) => update("agentLightContext", v)}
                label="Light context (skip heavy context loading)"
              />
            </div>
          </div>
        )}

        {form.payloadKind === "system_event" && (
          <div>
            <label className={LABEL_CLS}>Event text *</label>
            <textarea
              value={form.systemEventText}
              onChange={(e) => update("systemEventText", e.target.value)}
              rows={3}
              placeholder="Delivered to the heartbeat (wake_mode must be 'next-heartbeat')."
              className={INPUT_CLS}
            />
            {form.wakeMode !== "next-heartbeat" && (
              <p className="mt-1 text-xs text-amber-400">
                system_event is only delivered when wake_mode is
                &quot;next-heartbeat&quot;.
              </p>
            )}
          </div>
        )}
      </Section>

      {/* ----- Delivery ----- */}
      <Section title="Delivery" defaultOpen={false}>
        <div>
          <label className={LABEL_CLS}>Mode</label>
          <select
            value={form.deliveryMode}
            onChange={(e) =>
              update("deliveryMode", e.target.value as DeliveryMode)
            }
            className={INPUT_CLS}
          >
            <option value="none">none</option>
            <option value="announce">announce</option>
            <option value="webhook">webhook</option>
          </select>
        </div>

        {form.deliveryMode === "announce" && (
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className={LABEL_CLS}>Transport</label>
              {transports ? (
                <select
                  value={form.deliveryTransport}
                  onChange={(e) => update("deliveryTransport", e.target.value)}
                  className={INPUT_CLS}
                >
                  <option value="default">
                    (default — {transports.default})
                  </option>
                  {transports.transports.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={form.deliveryTransport}
                  onChange={(e) => update("deliveryTransport", e.target.value)}
                  placeholder="default"
                  className={INPUT_CLS}
                />
              )}
              {transportsError && (
                <p className="mt-1 text-xs text-amber-400">
                  Could not load transports ({transportsError}); using free-text input.
                </p>
              )}
            </div>
            <div>
              <label className={LABEL_CLS}>Channel</label>
              <input
                type="text"
                value={form.deliveryChannel}
                onChange={(e) => update("deliveryChannel", e.target.value)}
                placeholder="email / slack / sms"
                className={INPUT_CLS}
              />
            </div>
            <div>
              <label className={LABEL_CLS}>To</label>
              <input
                type="text"
                value={form.deliveryTo}
                onChange={(e) => update("deliveryTo", e.target.value)}
                placeholder="recipient"
                className={INPUT_CLS}
              />
            </div>
            <div>
              <label className={LABEL_CLS}>Account ID</label>
              <input
                type="text"
                value={form.deliveryAccountId}
                onChange={(e) => update("deliveryAccountId", e.target.value)}
                placeholder="optional"
                className={INPUT_CLS}
              />
            </div>
            <div className="flex items-end">
              <Toggle
                checked={form.deliveryBestEffort}
                onChange={(v) => update("deliveryBestEffort", v)}
                label="Best effort (don't fail on delivery error)"
              />
            </div>
          </div>
        )}

        {form.deliveryMode === "webhook" && (
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className={LABEL_CLS}>Webhook URL *</label>
              <input
                type="url"
                value={form.deliveryUrl}
                onChange={(e) => update("deliveryUrl", e.target.value)}
                placeholder="https://..."
                className={INPUT_CLS}
              />
            </div>
            <div className="flex items-end">
              <Toggle
                checked={form.deliveryBestEffort}
                onChange={(v) => update("deliveryBestEffort", v)}
                label="Best effort"
              />
            </div>
          </div>
        )}
      </Section>

      {/* ----- Advanced ----- */}
      <Section title="Advanced" defaultOpen={false}>
        <Toggle
          checked={form.deleteAfterRun}
          onChange={(v) => update("deleteAfterRun", v)}
          label="Delete cron after successful run"
        />

        <div className="border-t border-slate-700 pt-3">
          <Toggle
            checked={form.failureAlertEnabled}
            onChange={(v) => update("failureAlertEnabled", v)}
            label="Failure alert"
          />

          {form.failureAlertEnabled && (
            <div className="mt-3 grid gap-4 sm:grid-cols-2">
              <div>
                <label className={LABEL_CLS}>After N consecutive errors</label>
                <input
                  type="number"
                  min={1}
                  value={form.failureAfter}
                  onChange={(e) =>
                    update("failureAfter", Number(e.target.value) || 1)
                  }
                  className={INPUT_CLS}
                />
              </div>
              <div>
                <label className={LABEL_CLS}>Cooldown (seconds)</label>
                <input
                  type="number"
                  min={0}
                  value={form.failureCooldownSeconds}
                  onChange={(e) =>
                    update(
                      "failureCooldownSeconds",
                      Number(e.target.value) || 0,
                    )
                  }
                  className={INPUT_CLS}
                />
              </div>
              <div>
                <label className={LABEL_CLS}>Mode</label>
                <select
                  value={form.failureMode}
                  onChange={(e) =>
                    update(
                      "failureMode",
                      e.target.value as FormState["failureMode"],
                    )
                  }
                  className={INPUT_CLS}
                >
                  <option value="announce">announce</option>
                  <option value="webhook">webhook</option>
                </select>
              </div>
              {form.failureMode === "announce" ? (
                <>
                  <div className="sm:col-span-2">
                    <label className={LABEL_CLS}>Transport</label>
                    {transports ? (
                      <select
                        value={form.failureTransport}
                        onChange={(e) =>
                          update("failureTransport", e.target.value)
                        }
                        className={INPUT_CLS}
                      >
                        <option value="default">
                          (default — {transports.default})
                        </option>
                        {transports.transports.map((t) => (
                          <option key={t} value={t}>
                            {t}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type="text"
                        value={form.failureTransport}
                        onChange={(e) =>
                          update("failureTransport", e.target.value)
                        }
                        placeholder="default"
                        className={INPUT_CLS}
                      />
                    )}
                  </div>
                  <div>
                    <label className={LABEL_CLS}>Channel</label>
                    <input
                      type="text"
                      value={form.failureChannel}
                      onChange={(e) => update("failureChannel", e.target.value)}
                      className={INPUT_CLS}
                    />
                  </div>
                  <div>
                    <label className={LABEL_CLS}>To</label>
                    <input
                      type="text"
                      value={form.failureTo}
                      onChange={(e) => update("failureTo", e.target.value)}
                      className={INPUT_CLS}
                    />
                  </div>
                </>
              ) : (
                <div className="sm:col-span-2">
                  <label className={LABEL_CLS}>Webhook URL</label>
                  <input
                    type="url"
                    value={form.failureUrl}
                    onChange={(e) => update("failureUrl", e.target.value)}
                    placeholder="https://example.com/hook"
                    className={INPUT_CLS}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      </Section>

      {/* Actions */}
      <div className="flex items-center justify-between gap-3 pt-2">
        <div>
          {isEdit && (
            <button
              type="button"
              onClick={handleDelete}
              disabled={deleting || submitting}
              className="rounded-md border border-red-700 px-4 py-2 text-sm text-red-300 hover:bg-red-900/30 disabled:opacity-50 transition-colors"
            >
              {deleting ? "Deleting..." : "Delete"}
            </button>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-slate-600 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800 transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting || deleting}
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50 transition-colors"
          >
            {submitting
              ? isEdit
                ? "Saving..."
                : "Creating..."
              : isEdit
              ? "Save changes"
              : "Create Cron"}
          </button>
        </div>
      </div>
    </form>
  );
}
