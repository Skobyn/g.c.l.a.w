"use client";

import { useEffect, useState } from "react";
import type { AgentToolsSpec } from "@/types";
import { ChipInput } from "./chip-input";
import {
  INPUT_CLS,
  LABEL_CLS,
  SECTION_CLS,
  SaveBar,
  deepEqual,
} from "./shared";

const PROFILES = ["default", "minimal", "coding", "messaging", "full"] as const;

interface Props {
  value: AgentToolsSpec;
  onSave: (patch: { tools: AgentToolsSpec }) => Promise<void>;
  onDirtyChange: (dirty: boolean) => void;
}

export function TabTools({ value, onSave, onDirtyChange }: Props) {
  const [local, setLocal] = useState<AgentToolsSpec>(value);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLocal(value);
  }, [value]);

  const dirty = !deepEqual(local, value);
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await onSave({ tools: local });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className={SECTION_CLS}>
      <h2 className="text-lg font-semibold text-slate-100">Tools</h2>
      <p className="text-xs text-slate-500">
        Profile sets a baseline; allow adds tools on top; deny removes tools.
      </p>

      <div>
        <label className={LABEL_CLS}>Profile</label>
        <select
          className={INPUT_CLS}
          value={local.profile ?? ""}
          onChange={(e) =>
            setLocal({ ...local, profile: e.target.value || null })
          }
        >
          <option value="">(inherit)</option>
          {PROFILES.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className={LABEL_CLS}>Allow</label>
        <ChipInput
          values={local.allow}
          onChange={(v) => setLocal({ ...local, allow: v })}
          placeholder="tool name"
        />
      </div>

      <div>
        <label className={LABEL_CLS}>Deny</label>
        <ChipInput
          values={local.deny}
          onChange={(v) => setLocal({ ...local, deny: v })}
          placeholder="tool name"
        />
      </div>

      <SaveBar
        dirty={dirty}
        saving={saving}
        onSave={save}
        onReset={() => setLocal(value)}
        error={error}
      />
    </section>
  );
}
