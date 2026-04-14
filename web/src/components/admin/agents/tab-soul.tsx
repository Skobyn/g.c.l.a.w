"use client";

import { useEffect, useState } from "react";
import {
  INPUT_CLS,
  LABEL_CLS,
  SECTION_CLS,
  SaveBar,
} from "./shared";

interface Props {
  value: string | null;
  onSave: (patch: { soul_overlay: string | null }) => Promise<void>;
  onDirtyChange: (dirty: boolean) => void;
}

export function TabSoul({ value, onSave, onDirtyChange }: Props) {
  const [local, setLocal] = useState<string>(value ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLocal(value ?? "");
  }, [value]);

  const dirty = (local || null) !== value;
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await onSave({ soul_overlay: local || null });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className={SECTION_CLS}>
      <h2 className="text-lg font-semibold text-slate-100">Soul overlay</h2>
      <p className="text-xs text-slate-500">
        Agent-specific personality overlay. Layered on top of the base soul at
        runtime.
      </p>

      <div>
        <label className={LABEL_CLS}>Soul overlay (markdown)</label>
        <textarea
          className={`${INPUT_CLS} font-mono`}
          style={{ height: 360 }}
          value={local}
          onChange={(e) => setLocal(e.target.value)}
          placeholder="Leave empty to inherit the base soul for this agent."
        />
      </div>

      <SaveBar
        dirty={dirty}
        saving={saving}
        onSave={save}
        onReset={() => setLocal(value ?? "")}
        error={error}
      />
    </section>
  );
}
