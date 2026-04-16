"use client";

/**
 * Dropdown that lets the user pick which agent the chat view is
 * talking to. Fetches the live agent list from /admin/agents on
 * mount and defaults to "orchestrator".
 */

import { useEffect, useState } from "react";
import { useApiClient } from "@/lib/api-client";
import type { AgentListEntry } from "@/types";

export const DEFAULT_AGENT = "orchestrator";

interface AgentSelectorProps {
  /** Currently selected agent name. */
  value: string;
  /** Fires when the user picks a different agent. */
  onChange: (agentName: string) => void;
  /** Disable the dropdown (e.g. while a message is in flight). */
  disabled?: boolean;
}

export function AgentSelector({
  value,
  onChange,
  disabled = false,
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
        // Only show enabled agents. Keep orchestrator first so the
        // default is always visible at the top of the list.
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

  if (error) {
    return (
      <div className="text-xs text-red-300" title={error}>
        agents unavailable
      </div>
    );
  }

  return (
    <label className="flex items-center gap-2 text-sm text-slate-300">
      <span className="text-slate-400">Agent:</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled || loading}
        className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
        aria-label="Select agent"
      >
        {loading && agents.length === 0 ? (
          <option value={DEFAULT_AGENT}>loading…</option>
        ) : (
          agents.map((a) => (
            <option key={a.name} value={a.name}>
              {a.display_name || a.name}
            </option>
          ))
        )}
      </select>
    </label>
  );
}
