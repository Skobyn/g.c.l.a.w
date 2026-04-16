"use client";

/**
 * Agent selector — editorial radio cards stacked vertically.
 *
 * One agent per row. Name in Fraunces italic, mono handle underneath, role
 * blurb truncated. Active agent shows a signal-green rule + ACTIVE tag.
 */

import { useEffect, useState } from "react";
import { useApiClient } from "@/lib/api-client";
import type { AgentListEntry } from "@/types";

export const DEFAULT_AGENT = "orchestrator";

interface AgentSelectorProps {
  value: string;
  onChange: (agentName: string) => void;
  disabled?: boolean;
  /** When present, updates the parent with the active entry so the
   *  metadata rail can show the blurb without re-fetching. */
  onActiveEntry?: (entry: AgentListEntry | null) => void;
}

export function AgentSelector({
  value,
  onChange,
  disabled = false,
  onActiveEntry,
}: AgentSelectorProps) {
  const api = useApiClient();
  const [agents, setAgents] = useState<AgentListEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .listAgentsRich()
      .then((list) => {
        if (cancelled) return;
        const visible = list.filter((a) => a.enabled);
        visible.sort((a, b) => {
          if (a.name === DEFAULT_AGENT) return -1;
          if (b.name === DEFAULT_AGENT) return 1;
          return a.name.localeCompare(b.name);
        });
        setAgents(visible);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load agents");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  useEffect(() => {
    if (!onActiveEntry) return;
    const entry = agents.find((a) => a.name === value) ?? null;
    onActiveEntry(entry);
  }, [value, agents, onActiveEntry]);

  if (error) {
    return (
      <div className="label-caps text-alert" title={error}>
        AGENTS · OFFLINE
      </div>
    );
  }

  return (
    <div>
      <div className="label-caps mb-3">§ AGENT ROSTER</div>
      {loading && agents.length === 0 ? (
        <p className="font-mono text-[11px] text-paper-40">loading roster…</p>
      ) : (
        <ul className="flex flex-col">
          {agents.map((a) => {
            const isActive = a.name === value;
            const display = a.display_name || a.name;
            return (
              <li key={a.name}>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => onChange(a.name)}
                  className={`w-full text-left py-2.5 pr-2 pl-3 border-l transition-colors ${
                    isActive
                      ? "border-signal bg-signal-tint"
                      : "border-transparent hover:bg-ink-700"
                  } ${disabled ? "opacity-60 cursor-not-allowed" : ""}`}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span
                      className={`font-display italic text-[14.5px] ${
                        isActive ? "text-signal" : "text-paper"
                      }`}
                    >
                      {display}
                    </span>
                    {isActive && (
                      <span className="label-caps-signal shrink-0">ACTIVE</span>
                    )}
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-paper-40">
                    <span>{a.name}</span>
                    {a.heartbeat_enabled && (
                      <span className="flex items-center gap-1">
                        · <span className="phosphor-dot" /> HB
                      </span>
                    )}
                  </div>
                  {a.description && !isActive && (
                    <p className="mt-1 text-[12px] text-paper-60 line-clamp-1 font-body">
                      {a.description}
                    </p>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
