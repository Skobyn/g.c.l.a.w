"use client";

import { useState } from "react";
import type { EffectiveAgentConfig } from "@/types";
import { PROTECTED_AGENTS } from "@/types";
import { Banner, SECTION_CLS, Toggle, summarizeOverride } from "./shared";

interface Props {
  config: EffectiveAgentConfig;
  enabled: boolean;
  onToggleEnabled: (v: boolean) => Promise<void>;
  onRevert: () => Promise<void>;
  onDelete: () => Promise<void>;
  overrideTimestamps: { created_at: string; updated_at: string } | null;
}

export function TabOverview({
  config,
  enabled,
  onToggleEnabled,
  onRevert,
  onDelete,
  overrideTimestamps,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [confirmRevert, setConfirmRevert] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isProtected = (PROTECTED_AGENTS as readonly string[]).includes(
    config.name,
  );

  async function wrap(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Operation failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {isProtected && (
        <Banner tone="yellow">
          This is a built-in agent. Reverting the override restores the shipped
          default.
        </Banner>
      )}
      {config.is_standalone && (
        <Banner tone="blue">
          User-created agent. There is no baseline to revert to.
        </Banner>
      )}
      {error && <Banner tone="red">{error}</Banner>}

      <section className={SECTION_CLS}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              {config.identity.emoji && (
                <span className="text-2xl">{config.identity.emoji}</span>
              )}
              <h2 className="text-xl font-semibold text-slate-100">
                {config.identity.display_name || config.name}
              </h2>
            </div>
            <p className="mt-1 font-mono text-xs text-slate-500">
              {config.name}
            </p>
            {config.identity.description && (
              <p className="mt-2 text-sm text-slate-300">
                {config.identity.description}
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {config.has_override && !config.is_standalone && (
              <span className="rounded border border-indigo-700 bg-indigo-600/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-indigo-300">
                overridden
              </span>
            )}
            {config.is_standalone && (
              <span className="rounded border border-teal-700 bg-teal-600/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-teal-300">
                custom
              </span>
            )}
            {config.has_baseline && (
              <span className="rounded border border-slate-600 bg-slate-800 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-slate-300">
                baseline
              </span>
            )}
            {isProtected && (
              <span className="rounded border border-amber-700 bg-amber-900/30 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-300">
                protected
              </span>
            )}
          </div>
        </div>

        <div className="border-t border-slate-700 pt-3">
          <Toggle
            checked={enabled}
            onChange={(v) => wrap(() => onToggleEnabled(v))}
            label={enabled ? "Enabled" : "Disabled"}
            disabled={busy}
          />
        </div>

        {overrideTimestamps && (
          <div className="border-t border-slate-700 pt-3 text-xs text-slate-500">
            Override created{" "}
            {new Date(overrideTimestamps.created_at).toLocaleString()} · updated{" "}
            {new Date(overrideTimestamps.updated_at).toLocaleString()}
          </div>
        )}
      </section>

      <section className={SECTION_CLS}>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Danger zone
        </h3>
        <p className="text-xs text-slate-500">
          {summarizeOverride(null /* caller passes override elsewhere */)}
        </p>
        <div className="flex flex-wrap gap-2">
          {config.has_override && config.has_baseline && !config.is_standalone && (
            <>
              {!confirmRevert ? (
                <button
                  type="button"
                  onClick={() => setConfirmRevert(true)}
                  className="rounded-md border border-amber-700 px-3 py-2 text-sm text-amber-300 hover:bg-amber-900/30"
                >
                  Revert to baseline
                </button>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-amber-300">
                    Discard override and restore shipped defaults?
                  </span>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      wrap(async () => {
                        await onRevert();
                        setConfirmRevert(false);
                      })
                    }
                    className="rounded-md bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-500"
                  >
                    Confirm revert
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmRevert(false)}
                    className="text-xs text-slate-400 hover:text-slate-200"
                  >
                    Cancel
                  </button>
                </div>
              )}
            </>
          )}
          {(config.is_standalone || isProtected) && (
            <>
              {!confirmDelete ? (
                <button
                  type="button"
                  onClick={() => setConfirmDelete(true)}
                  className="rounded-md border border-red-700 px-3 py-2 text-sm text-red-300 hover:bg-red-900/30"
                >
                  Delete agent
                </button>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-red-300">
                    {isProtected
                      ? "Force delete a protected agent?"
                      : "Permanently delete this agent?"}
                  </span>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      wrap(async () => {
                        await onDelete();
                      })
                    }
                    className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-500"
                  >
                    Confirm delete
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmDelete(false)}
                    className="text-xs text-slate-400 hover:text-slate-200"
                  >
                    Cancel
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </section>
    </div>
  );
}
