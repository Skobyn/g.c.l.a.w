"use client";

import { useEffect, useState } from "react";
import type { AgentIdentity } from "@/types";
import { INPUT_CLS, LABEL_CLS, SECTION_CLS, SaveBar, deepEqual } from "./shared";

interface Props {
  value: AgentIdentity;
  onSave: (patch: { identity: AgentIdentity }) => Promise<void>;
  onDirtyChange: (dirty: boolean) => void;
}

export function TabIdentity({ value, onSave, onDirtyChange }: Props) {
  const [local, setLocal] = useState<AgentIdentity>(value);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLocal(value);
  }, [value]);

  const dirty = !deepEqual(local, value);
  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  function update<K extends keyof AgentIdentity>(
    k: K,
    v: AgentIdentity[K],
  ) {
    setLocal((prev) => ({ ...prev, [k]: v }));
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await onSave({ identity: local });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className={SECTION_CLS}>
      <h2 className="text-lg font-semibold text-slate-100">Identity</h2>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <label className={LABEL_CLS}>Display name</label>
          <input
            type="text"
            className={INPUT_CLS}
            value={local.display_name ?? ""}
            onChange={(e) =>
              update("display_name", e.target.value || null)
            }
          />
        </div>
        <div>
          <label className={LABEL_CLS}>Emoji</label>
          <input
            type="text"
            maxLength={4}
            className={INPUT_CLS}
            placeholder="🤖"
            value={local.emoji ?? ""}
            onChange={(e) => update("emoji", e.target.value || null)}
          />
        </div>
        <div className="md:col-span-2">
          <label className={LABEL_CLS}>Avatar URL</label>
          <input
            type="text"
            className={INPUT_CLS}
            value={local.avatar_url ?? ""}
            onChange={(e) =>
              update("avatar_url", e.target.value || null)
            }
          />
        </div>
        <div className="md:col-span-2">
          <label className={LABEL_CLS}>Description</label>
          <textarea
            className={`${INPUT_CLS} h-24`}
            value={local.description ?? ""}
            onChange={(e) =>
              update("description", e.target.value || null)
            }
          />
        </div>
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
