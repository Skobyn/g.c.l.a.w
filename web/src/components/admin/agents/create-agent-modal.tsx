"use client";

import { useState } from "react";
import type { CreateAgentPayload } from "@/types";
import { INPUT_CLS, LABEL_CLS, Toggle } from "./shared";

const AGENT_NAME_RE = /^[a-z0-9][a-z0-9_-]*$/;

const TEMPLATE = `# Role
Describe the agent's purpose in one paragraph.

## Responsibilities
- Responsibility 1
- Responsibility 2

## Tools & Authority
- What tools can this agent use?
- When should it escalate?

## Communication Style
- Tone, format, verbosity preferences.
`;

interface Props {
  onCreate: (body: CreateAgentPayload) => Promise<void>;
  onClose: () => void;
}

export function CreateAgentModal({ onCreate, onClose }: Props) {
  const [agentName, setAgentName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [body, setBody] = useState(TEMPLATE);
  const [heartbeatEnabled, setHeartbeatEnabled] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const nameValid = AGENT_NAME_RE.test(agentName);
  const canSubmit = nameValid && body.trim().length > 0 && !submitting;

  async function submit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const payload: CreateAgentPayload = {
        agent_name: agentName,
        body,
      };
      if (displayName) payload.display_name = displayName;
      if (heartbeatEnabled) payload.heartbeat = { enabled: true };
      await onCreate(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create agent");
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-lg border border-slate-700 bg-slate-900 shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-700 px-5 py-3">
          <h2 className="text-base font-semibold text-slate-100">
            Create Agent
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="space-y-4 overflow-y-auto px-5 py-4">
          <div>
            <label className={LABEL_CLS}>Agent name (required)</label>
            <input
              type="text"
              className={INPUT_CLS}
              value={agentName}
              onChange={(e) => setAgentName(e.target.value)}
              placeholder="e.g. research-assistant"
            />
            <p className="mt-1 text-[11px] text-slate-500">
              Lowercase letters, numbers, hyphens, underscores.
              {agentName && !nameValid && (
                <span className="ml-2 text-red-400">Invalid name.</span>
              )}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={LABEL_CLS}>Display name</label>
              <input
                type="text"
                className={INPUT_CLS}
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Research Assistant"
              />
            </div>
            <div>
              <label className={LABEL_CLS}>Description</label>
              <input
                type="text"
                className={INPUT_CLS}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Short summary"
              />
            </div>
          </div>

          <div>
            <label className={LABEL_CLS}>Instructions body (required)</label>
            <textarea
              className={`${INPUT_CLS} h-72 font-mono`}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </div>

          <Toggle
            checked={heartbeatEnabled}
            onChange={setHeartbeatEnabled}
            label="Enable heartbeat (defaults)"
          />

          {error && (
            <div className="rounded-md border border-red-700 bg-red-900/30 px-3 py-2 text-xs text-red-300">
              {error}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 border-t border-slate-700 px-5 py-3">
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
            disabled={!canSubmit}
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {submitting ? "Creating..." : "Create Agent"}
          </button>
        </div>
      </div>
    </div>
  );
}
