"use client";

import { useEffect, useState } from "react";
import type { AgentHeartbeatConfig } from "@/types";
import {
  INPUT_CLS,
  LABEL_CLS,
  SECTION_CLS,
  SaveBar,
  Toggle,
  deepEqual,
} from "./shared";

const DEFAULT_HB: AgentHeartbeatConfig = {
  enabled: false,
  every: "30m",
  prompt: null,
  session: "main",
  isolated_session: false,
  light_context: false,
  timeout_seconds: 60,
  ack_max_chars: 2000,
  active_hours: null,
  target: "none",
  channel: null,
  include_reasoning: false,
};

interface Props {
  value: AgentHeartbeatConfig | null;
  onSave: (patch: {
    heartbeat: AgentHeartbeatConfig | null;
  }) => Promise<void>;
  onDirtyChange: (dirty: boolean) => void;
}

export function TabHeartbeat({ value, onSave, onDirtyChange }: Props) {
  const [local, setLocal] = useState<AgentHeartbeatConfig>(value ?? DEFAULT_HB);
  const [hasHb, setHasHb] = useState<boolean>(value !== null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLocal(value ?? DEFAULT_HB);
    setHasHb(value !== null);
  }, [value]);

  const computed: AgentHeartbeatConfig | null = hasHb ? local : null;
  const dirty = !deepEqual(computed, value);
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  function patch<K extends keyof AgentHeartbeatConfig>(
    k: K,
    v: AgentHeartbeatConfig[K],
  ) {
    setLocal((prev) => ({ ...prev, [k]: v }));
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await onSave({ heartbeat: computed });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  const activeHours = local.active_hours;

  return (
    <section className={SECTION_CLS}>
      <h2 className="text-lg font-semibold text-slate-100">Heartbeat</h2>

      <Toggle
        checked={hasHb}
        onChange={setHasHb}
        label="Configure heartbeat for this agent"
      />

      {hasHb && (
        <>
          <Toggle
            checked={local.enabled}
            onChange={(v) => patch("enabled", v)}
            label="Enabled"
          />

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label className={LABEL_CLS}>Every</label>
              <input
                type="text"
                className={INPUT_CLS}
                value={local.every}
                onChange={(e) => patch("every", e.target.value)}
                placeholder="30m, 2h, 15s"
              />
            </div>
            <div>
              <label className={LABEL_CLS}>Session mode</label>
              <input
                type="text"
                className={INPUT_CLS}
                value={local.session}
                onChange={(e) => patch("session", e.target.value)}
                placeholder="main | isolated | global | custom-key"
              />
            </div>
            <div>
              <label className={LABEL_CLS}>Timeout (seconds)</label>
              <input
                type="number"
                className={INPUT_CLS}
                value={local.timeout_seconds}
                onChange={(e) =>
                  patch("timeout_seconds", Number(e.target.value) || 0)
                }
              />
            </div>
            <div>
              <label className={LABEL_CLS}>Ack max chars</label>
              <input
                type="number"
                className={INPUT_CLS}
                value={local.ack_max_chars}
                onChange={(e) =>
                  patch("ack_max_chars", Number(e.target.value) || 0)
                }
              />
            </div>
          </div>

          <div>
            <label className={LABEL_CLS}>Prompt</label>
            <textarea
              className={`${INPUT_CLS} h-24`}
              value={local.prompt ?? ""}
              onChange={(e) => patch("prompt", e.target.value || null)}
            />
          </div>

          <div className="space-y-2">
            <Toggle
              checked={local.isolated_session}
              onChange={(v) => patch("isolated_session", v)}
              label="Isolated session"
            />
            <Toggle
              checked={local.light_context}
              onChange={(v) => patch("light_context", v)}
              label="Light context"
            />
            <Toggle
              checked={local.include_reasoning}
              onChange={(v) => patch("include_reasoning", v)}
              label="Include reasoning"
            />
          </div>

          <div>
            <label className={LABEL_CLS}>Active hours</label>
            <div className="flex flex-wrap items-center gap-2">
              <Toggle
                checked={activeHours !== null}
                onChange={(v) =>
                  patch(
                    "active_hours",
                    v
                      ? {
                          start: "09:00",
                          end: "18:00",
                          timezone: "America/Los_Angeles",
                        }
                      : null,
                  )
                }
                label="Restrict to hours"
              />
              {activeHours && (
                <>
                  <input
                    type="text"
                    className={`${INPUT_CLS} w-24`}
                    value={activeHours.start}
                    onChange={(e) =>
                      patch("active_hours", {
                        ...activeHours,
                        start: e.target.value,
                      })
                    }
                    placeholder="09:00"
                  />
                  <span className="text-slate-500">—</span>
                  <input
                    type="text"
                    className={`${INPUT_CLS} w-24`}
                    value={activeHours.end}
                    onChange={(e) =>
                      patch("active_hours", {
                        ...activeHours,
                        end: e.target.value,
                      })
                    }
                    placeholder="18:00"
                  />
                  <input
                    type="text"
                    className={`${INPUT_CLS} w-48`}
                    value={activeHours.timezone}
                    onChange={(e) =>
                      patch("active_hours", {
                        ...activeHours,
                        timezone: e.target.value,
                      })
                    }
                    placeholder="America/Los_Angeles"
                  />
                </>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label className={LABEL_CLS}>Target</label>
              <select
                className={INPUT_CLS}
                value={local.target}
                onChange={(e) =>
                  patch(
                    "target",
                    e.target.value as AgentHeartbeatConfig["target"],
                  )
                }
              >
                <option value="none">none</option>
                <option value="last">last</option>
                <option value="channel">channel</option>
              </select>
            </div>
            {local.target === "channel" && (
              <div>
                <label className={LABEL_CLS}>Channel</label>
                <input
                  type="text"
                  className={INPUT_CLS}
                  value={local.channel ?? ""}
                  onChange={(e) => patch("channel", e.target.value || null)}
                />
              </div>
            )}
          </div>
        </>
      )}

      <SaveBar
        dirty={dirty}
        saving={saving}
        onSave={save}
        onReset={() => {
          setLocal(value ?? DEFAULT_HB);
          setHasHb(value !== null);
        }}
        error={error}
      />
    </section>
  );
}
