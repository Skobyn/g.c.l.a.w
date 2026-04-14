"use client";

/**
 * Modal that lists the provider kind's preset models with checkboxes.
 * Submitting calls installPresets and returns the created models.
 */

import { useMemo, useState } from "react";
import type { CatalogModel, Presets, Provider } from "@/types";
import { Modal, ErrorBanner } from "./shared";

interface PresetInstallDialogProps {
  provider: Provider;
  presets: Presets | null;
  existingModelIds: Set<string>;
  onInstall: (modelIds: string[]) => Promise<CatalogModel[]>;
  onClose: () => void;
}

export function PresetInstallDialog({
  provider,
  presets,
  existingModelIds,
  onInstall,
  onClose,
}: PresetInstallDialogProps) {
  const models = useMemo(
    () => presets?.providers?.[provider.kind]?.models ?? [],
    [presets, provider.kind],
  );
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function submit() {
    if (selected.size === 0) {
      setError("Select at least one preset to install.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onInstall(Array.from(selected));
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to install presets");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={`Install presets — ${provider.name}`}
      onClose={onClose}
      wide
    >
      <div className="space-y-4">
        <ErrorBanner error={error} />
        {models.length === 0 ? (
          <div className="rounded-md border border-slate-700 bg-slate-900/60 px-4 py-8 text-center text-sm text-slate-500">
            No presets available for this provider kind.
          </div>
        ) : (
          <div className="max-h-96 space-y-1 overflow-y-auto rounded-md border border-slate-700 bg-slate-900/40 p-2">
            {models.map((m) => {
              const already = existingModelIds.has(m.model_id);
              const checked = selected.has(m.model_id);
              return (
                <label
                  key={m.model_id}
                  className={`flex items-start gap-3 rounded-md px-3 py-2 text-sm ${
                    already
                      ? "opacity-50"
                      : "cursor-pointer hover:bg-slate-800/60"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={already}
                    onChange={() => toggle(m.model_id)}
                    className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-900 text-indigo-500 focus:ring-indigo-500"
                  />
                  <div className="flex-1">
                    <div className="font-medium text-slate-200">
                      {m.display_name}
                      {already && (
                        <span className="ml-2 text-xs text-slate-500">
                          (already installed)
                        </span>
                      )}
                    </div>
                    <div className="font-mono text-xs text-slate-500">
                      {m.model_id}
                    </div>
                    <div className="mt-0.5 flex flex-wrap gap-2 text-[10px] text-slate-500">
                      {m.context_window != null && (
                        <span>ctx {m.context_window.toLocaleString()}</span>
                      )}
                      {m.max_output_tokens != null && (
                        <span>out {m.max_output_tokens.toLocaleString()}</span>
                      )}
                      {m.capabilities?.vision && <span>vision</span>}
                      {m.capabilities?.tools && <span>tools</span>}
                      {m.capabilities?.reasoning && <span>reasoning</span>}
                    </div>
                  </div>
                </label>
              );
            })}
          </div>
        )}

        <div className="flex justify-end gap-3 border-t border-slate-700 pt-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-600 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={busy || selected.size === 0}
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {busy
              ? "Installing..."
              : `Install ${selected.size} model${selected.size === 1 ? "" : "s"}`}
          </button>
        </div>
      </div>
    </Modal>
  );
}
