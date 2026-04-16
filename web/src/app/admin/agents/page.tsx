"use client";

/**
 * /admin/agents — editorial index of the roster.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/layout/app-shell";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";
import type { AgentListEntry, CreateAgentPayload } from "@/types";
import { AgentListCard } from "@/components/admin/agents/agent-list-card";
import { CreateAgentModal } from "@/components/admin/agents/create-agent-modal";
import { Banner } from "@/components/admin/agents/shared";

const WORD_NUMS = [
  "ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN",
  "EIGHT", "NINE", "TEN", "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN",
  "FIFTEEN", "SIXTEEN", "SEVENTEEN", "EIGHTEEN", "NINETEEN", "TWENTY",
];

function numberWord(n: number): string {
  if (n >= 0 && n < WORD_NUMS.length) return WORD_NUMS[n];
  return n.toString();
}

function AgentsContent() {
  const { getIdToken } = useAuth();
  const router = useRouter();
  const api = useMemo(() => createApiClient(getIdToken), [getIdToken]);

  const [entries, setEntries] = useState<AgentListEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.listAgentsRich();
      setEntries(list);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agents");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate(body: CreateAgentPayload) {
    await api.createAgent(body);
    setShowCreate(false);
    await load();
    router.push(`/admin/agents/${encodeURIComponent(body.agent_name)}`);
  }

  const count = entries.length;
  const word = numberWord(count).toLowerCase();

  return (
    <div className="flex h-full flex-col bg-ink-900 text-paper">
      <header className="hairline-b px-8 pt-8 pb-6">
        <div className="flex items-end justify-between gap-4">
          <div>
            <div className="label-caps mb-1.5">§ 07 · ROSTER</div>
            <h1 className="font-display text-[36px] italic leading-none">
              Agents — a register of
              <br />
              the <span className="not-italic text-signal">{word}</span>.
            </h1>
            <p className="mt-3 max-w-[520px] font-body text-[13px] text-paper-60 leading-relaxed">
              Baseline agents, overrides, and user-created agents. Every agent is
              an <em className="italic text-paper">agent.md</em> bound to a{" "}
              <em className="italic text-paper">soul.md</em>. They speak to the
              board, not to each other.
            </p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="btn-hair-signal"
          >
            + Commission Agent
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto px-8 py-4">
        {error && (
          <div className="my-4">
            <Banner tone="red">{error}</Banner>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-24">
            <p className="font-mono text-[11px] uppercase tracking-widest text-paper-40">
              LOADING ROSTER<span className="signal-cursor" />
            </p>
          </div>
        ) : entries.length === 0 ? (
          <div className="py-16 text-center font-mono text-[11px] uppercase tracking-widest text-paper-40">
            — THE REGISTER IS EMPTY —
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-10">
            {entries.map((e, i) => (
              <AgentListCard key={e.name} entry={e} index={i} />
            ))}
          </div>
        )}
      </main>

      {showCreate && (
        <CreateAgentModal
          onCreate={handleCreate}
          onClose={() => setShowCreate(false)}
        />
      )}
    </div>
  );
}

export default function AgentsAdminPage() {
  return (
    <AppShell>
      <AgentsContent />
    </AppShell>
  );
}
