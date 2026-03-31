"use client";

/**
 * Card for a single agent showing name, soul overlay status,
 * an expandable soul file editor, and heartbeat log timeline.
 */

import { useState } from "react";
import type { AgentInfo, HeartbeatLogEntry } from "@/types";
import { SoulEditor } from "./soul-editor";
import { HeartbeatTimeline } from "./heartbeat-timeline";

interface AgentCardProps {
  agent: AgentInfo;
  heartbeatLogs: HeartbeatLogEntry[];
}

export function AgentCard({ agent, heartbeatLogs }: AgentCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<"soul" | "heartbeat">("soul");

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800 overflow-hidden">
      {/* Card header */}
      <div
        className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-slate-750 transition-colors"
        onClick={() => setExpanded((prev) => !prev)}
      >
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-full bg-indigo-600 flex items-center justify-center text-white font-bold text-sm uppercase">
            {agent.name.charAt(0)}
          </div>
          <div>
            <p className="font-semibold text-slate-100">{agent.name}</p>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span
                className={`h-2 w-2 rounded-full ${agent.has_soul_overlay ? "bg-green-400" : "bg-slate-500"}`}
              />
              <span className="text-xs text-slate-400">
                {agent.has_soul_overlay ? "Soul overlay active" : "No soul overlay"}
              </span>
            </div>
          </div>
        </div>
        <svg
          className={`h-5 w-5 text-slate-400 transition-transform ${expanded ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </div>

      {/* Expanded body */}
      {expanded && (
        <div className="border-t border-slate-700">
          {/* Tabs */}
          <div className="flex border-b border-slate-700">
            <button
              onClick={() => setActiveTab("soul")}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === "soul"
                  ? "text-indigo-400 border-b-2 border-indigo-400"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Soul Overlay
            </button>
            <button
              onClick={() => setActiveTab("heartbeat")}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === "heartbeat"
                  ? "text-indigo-400 border-b-2 border-indigo-400"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Heartbeat Logs
            </button>
          </div>

          <div className="p-4">
            {activeTab === "soul" ? (
              <SoulEditor agentName={agent.name} />
            ) : (
              <HeartbeatTimeline logs={heartbeatLogs} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
