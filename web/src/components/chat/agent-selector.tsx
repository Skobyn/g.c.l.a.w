"use client";

/**
 * Agent selector — collapsible tree with orchestrator at the top.
 *
 * Watson (orchestrator) is always visible. Sub-agents are grouped in
 * a collapsible "SUB AGENTS" folder. If any sub-agent is a manager
 * (name ends with `-mgr`), it could in turn have nested specialists,
 * shown in their own collapsible folder.
 */

import { useEffect, useState, useCallback } from "react";
import { useApiClient } from "@/lib/api-client";
import type { AgentListEntry } from "@/types";

export const DEFAULT_AGENT = "orchestrator";

interface AgentSelectorProps {
  value: string;
  onChange: (agentName: string) => void;
  disabled?: boolean;
  onActiveEntry?: (entry: AgentListEntry | null) => void;
}

/** A single agent button row. */
function AgentRow({
  entry,
  isActive,
  disabled,
  depth,
  onChange,
}: {
  entry: AgentListEntry;
  isActive: boolean;
  disabled: boolean;
  depth: number;
  onChange: (name: string) => void;
}) {
  const display = entry.display_name || entry.name;
  return (
    <li>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onChange(entry.name)}
        className={`w-full text-left py-2.5 pr-2 border-l transition-colors ${
          isActive
            ? "border-signal bg-signal-tint"
            : "border-transparent hover:bg-ink-700"
        } ${disabled ? "opacity-60 cursor-not-allowed" : ""}`}
        style={{ paddingLeft: `${12 + depth * 16}px` }}
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
          <span>{entry.name}</span>
          {entry.heartbeat_enabled && (
            <span className="flex items-center gap-1">
              · <span className="phosphor-dot" /> HB
            </span>
          )}
        </div>
        {entry.description && !isActive && (
          <p className="mt-1 text-[12px] text-paper-60 line-clamp-1 font-body">
            {entry.description}
          </p>
        )}
      </button>
    </li>
  );
}

/** Collapsible folder node. */
function AgentFolder({
  label,
  count,
  depth,
  defaultOpen,
  children,
}: {
  label: string;
  count: number;
  depth: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen ?? false);

  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full text-left py-2 pr-2 border-l border-transparent hover:bg-ink-700 transition-colors flex items-center gap-2"
        style={{ paddingLeft: `${12 + depth * 16}px` }}
      >
        <span className="font-mono text-[10px] text-paper-40 w-3 shrink-0">
          {open ? "▾" : "▸"}
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-paper-60">
          {label}
        </span>
        <span className="font-mono text-[10px] text-paper-40 ml-auto">
          {count.toString().padStart(2, "0")}
        </span>
      </button>
      {open && <ul className="flex flex-col">{children}</ul>}
    </li>
  );
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
        visible.sort((a, b) => a.name.localeCompare(b.name));
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

  const handleChange = useCallback(
    (name: string) => {
      if (!disabled) onChange(name);
    },
    [disabled, onChange],
  );

  if (error) {
    return (
      <div className="label-caps text-alert" title={error}>
        AGENTS · OFFLINE
      </div>
    );
  }

  const orchestrator = agents.find((a) => a.name === DEFAULT_AGENT);
  const subAgents = agents.filter((a) => a.name !== DEFAULT_AGENT);

  const hasActiveSubAgent = subAgents.some((a) => a.name === value);

  return (
    <div>
      <div className="label-caps mb-3">§ AGENT ROSTER</div>
      {loading && agents.length === 0 ? (
        <p className="font-mono text-[11px] text-paper-40">loading roster…</p>
      ) : (
        <ul className="flex flex-col">
          {orchestrator && (
            <AgentRow
              entry={orchestrator}
              isActive={value === DEFAULT_AGENT}
              disabled={disabled}
              depth={0}
              onChange={handleChange}
            />
          )}

          {subAgents.length > 0 && (
            <AgentFolder
              label="SUB AGENTS"
              count={subAgents.length}
              depth={0}
              defaultOpen={hasActiveSubAgent}
            >
              {subAgents.map((a) => (
                <AgentRow
                  key={a.name}
                  entry={a}
                  isActive={a.name === value}
                  disabled={disabled}
                  depth={1}
                  onChange={handleChange}
                />
              ))}
            </AgentFolder>
          )}
        </ul>
      )}
    </div>
  );
}
