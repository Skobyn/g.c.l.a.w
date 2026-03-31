"use client";

/**
 * Expandable card for a single skill showing all metadata.
 */

import { useState } from "react";
import type { SkillInfo } from "@/types";

interface SkillCardProps {
  skill: SkillInfo;
}

const SOURCE_BADGE: Record<SkillInfo["source"], string> = {
  builtin: "bg-slate-700 text-slate-300",
  imported: "bg-blue-900/60 text-blue-300",
  custom: "bg-indigo-900/60 text-indigo-300",
};

const TRIGGER_BADGE: Record<string, string> = {
  auto: "bg-green-900/60 text-green-300",
  manual: "bg-yellow-900/60 text-yellow-300",
  both: "bg-purple-900/60 text-purple-300",
};

function Badge({ label, className }: { label: string; className: string }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${className}`}>
      {label}
    </span>
  );
}

function ConfigSection({ config }: { config: Record<string, unknown> }) {
  const entries = Object.entries(config);
  if (entries.length === 0) return <span className="text-xs text-slate-500 italic">None</span>;
  return (
    <pre className="rounded bg-slate-900 px-3 py-2 text-xs text-slate-300 overflow-x-auto">
      {JSON.stringify(config, null, 2)}
    </pre>
  );
}

export function SkillCard({ skill }: SkillCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800 overflow-hidden">
      {/* Header */}
      <div
        className="flex items-start justify-between px-4 py-3 cursor-pointer hover:bg-slate-750 transition-colors"
        onClick={() => setExpanded((prev) => !prev)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-semibold text-slate-100">{skill.name}</p>
            <Badge label={`v${skill.version}`} className="bg-slate-700 text-slate-300" />
            <Badge label={skill.source} className={SOURCE_BADGE[skill.source]} />
            <Badge label={skill.trigger.mode} className={TRIGGER_BADGE[skill.trigger.mode] || "bg-slate-700 text-slate-300"} />
          </div>
          <p className="mt-1 text-sm text-slate-400 line-clamp-2">{skill.description}</p>
        </div>
        <svg
          className={`ml-3 h-5 w-5 flex-shrink-0 text-slate-400 transition-transform ${expanded ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="border-t border-slate-700 px-4 py-4 space-y-4">
          {/* Trigger details */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Trigger</h4>
            <div className="grid gap-1 text-sm">
              <div className="flex gap-2">
                <span className="text-slate-400 w-20 flex-shrink-0">Mode:</span>
                <span className="text-slate-200">{skill.trigger.mode}</span>
              </div>
              {skill.trigger.command && (
                <div className="flex gap-2">
                  <span className="text-slate-400 w-20 flex-shrink-0">Command:</span>
                  <code className="text-indigo-300 text-xs">{skill.trigger.command}</code>
                </div>
              )}
              {skill.trigger.contexts.length > 0 && (
                <div className="flex gap-2">
                  <span className="text-slate-400 w-20 flex-shrink-0">Contexts:</span>
                  <div className="flex flex-wrap gap-1">
                    {skill.trigger.contexts.map((ctx) => (
                      <span key={ctx} className="rounded bg-slate-700 px-1.5 py-0.5 text-xs text-slate-300">{ctx}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Tools required */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Tools Required</h4>
            {skill.tools_required.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {skill.tools_required.map((tool) => (
                  <span key={tool} className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-300">{tool}</span>
                ))}
              </div>
            ) : (
              <span className="text-xs text-slate-500 italic">None</span>
            )}
          </div>

          {/* Agents granted */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Agents Granted</h4>
            {skill.agents_granted.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {skill.agents_granted.map((agent) => (
                  <span key={agent} className="rounded bg-indigo-900/50 px-2 py-0.5 text-xs text-indigo-300">{agent}</span>
                ))}
              </div>
            ) : (
              <span className="text-xs text-slate-500 italic">None</span>
            )}
          </div>

          {/* Config */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Config</h4>
            <ConfigSection config={skill.config} />
          </div>
        </div>
      )}
    </div>
  );
}
