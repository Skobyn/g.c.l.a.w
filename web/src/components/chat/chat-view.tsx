"use client";

/**
 * Chat — editorial two-column transcript.
 *
 *   ┌────────────────────────────┬───────────────┐
 *   │ TRANSCRIPT (2/3)           │ METADATA RAIL │
 *   │                            │ session stats │
 *   │ dateline · agent           │ agent brief   │
 *   │ ─── body ─────             │ tools invoked │
 *   │                            │ agent roster  │
 *   └────────────────────────────┴───────────────┘
 */

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { useAuth } from "@/contexts/auth-context";
import { createApiClient } from "@/lib/api-client";
import { useChatRunStream } from "@/lib/use-chat-run-stream";
import { useUserEvents } from "@/lib/use-user-events";
import { MessageList } from "./message-list";
import { MessageInput } from "./message-input";
import { VoiceControls } from "./voice-controls";
import { AgentSelector, DEFAULT_AGENT } from "./agent-selector";
import { BoardSummaryCard } from "./board-summary-card";
import {
  DelegationStreamOverlay,
  useDelegationStream,
} from "./delegation-stream";
import type { AgentListEntry, ChatMessage } from "@/types";
import { formatDatestamp } from "@/lib/format";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

function msgId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

const SESSION_KEY = "gclaw_session_id";

function newSessionId(): string {
  return `sess_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function getBaseSessionId(): string {
  let sessionId = localStorage.getItem(SESSION_KEY);
  if (!sessionId) {
    sessionId = newSessionId();
    localStorage.setItem(SESSION_KEY, sessionId);
  }
  return sessionId;
}

function resetBaseSessionId(): string {
  const sid = newSessionId();
  localStorage.setItem(SESSION_KEY, sid);
  return sid;
}

export function ChatView() {
  const { getIdToken } = useAuth();
  const [messagesByAgent, setMessagesByAgent] = useState<
    Record<string, ChatMessage[]>
  >({});
  const [activeAgent, setActiveAgent] = useState<string>(DEFAULT_AGENT);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeEntry, setActiveEntry] = useState<AgentListEntry | null>(null);
  const [sessionId, setSessionId] = useState<string>("");
  // Rendered only after mount so the server-side HTML (no Date) matches
  // the first client render — avoids React hydration mismatch (#425/#418).
  const [headerDatestamp, setHeaderDatestamp] = useState<string>("");
  const clientRef = useRef(createApiClient(getIdToken));

  useEffect(() => {
    clientRef.current = createApiClient(getIdToken);
  }, [getIdToken]);

  useEffect(() => {
    setSessionId(getBaseSessionId());
    setHeaderDatestamp(
      formatDatestamp(new Date(), { withTime: true, withDay: true }),
    );
    const id = setInterval(() => {
      setHeaderDatestamp(
        formatDatestamp(new Date(), { withTime: true, withDay: true }),
      );
    }, 60_000);
    return () => clearInterval(id);
  }, []);

  const messages = useMemo(
    () => messagesByAgent[activeAgent] || [],
    [messagesByAgent, activeAgent],
  );

  const loadHistory = useCallback(
    async (agent: string) => {
      if (messagesByAgent[agent] !== undefined) return;
      try {
        const sid = getBaseSessionId();
        const resp = await clientRef.current.getChatHistory(
          sid,
          agent === DEFAULT_AGENT ? null : agent,
        );
        const loaded: ChatMessage[] = resp.messages.map((m) => ({
          id: msgId(),
          role: m.role === "assistant" ? "assistant" : "user",
          content: m.content,
          timestamp: m.timestamp ? new Date(m.timestamp) : new Date(),
        }));
        setMessagesByAgent((prev) =>
          prev[agent] !== undefined ? prev : { ...prev, [agent]: loaded },
        );
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn("failed to load chat history for", agent, err);
        setMessagesByAgent((prev) =>
          prev[agent] !== undefined ? prev : { ...prev, [agent]: [] },
        );
      }
    },
    [messagesByAgent],
  );

  useEffect(() => {
    void loadHistory(DEFAULT_AGENT);
  }, [loadHistory]);

  const handleAgentChange = useCallback(
    (name: string) => {
      setActiveAgent(name);
      setError(null);
      void loadHistory(name);
    },
    [loadHistory],
  );

  const handleNewConversation = useCallback(() => {
    const sid = resetBaseSessionId();
    setSessionId(sid);
    setMessagesByAgent({});
    setError(null);
    void loadHistory(activeAgent);
  }, [activeAgent, loadHistory]);

  const handleSend = useCallback(
    async (content: string) => {
      const agent = activeAgent;
      const userMsg: ChatMessage = {
        id: msgId(),
        role: "user",
        content,
        timestamp: new Date(),
      };
      setMessagesByAgent((prev) => ({
        ...prev,
        [agent]: [...(prev[agent] || []), userMsg],
      }));
      setIsLoading(true);
      setError(null);

      try {
        const sid = getBaseSessionId();
        const response = await clientRef.current.chat(
          sid,
          content,
          agent === DEFAULT_AGENT ? null : agent,
        );

        const assistantMsg: ChatMessage = {
          id: msgId(),
          role: "assistant",
          content: response.text,
          timestamp: new Date(),
          tool_calls: response.tool_calls,
          run_id: response.run_id,
        };
        setMessagesByAgent((prev) => ({
          ...prev,
          [agent]: [...(prev[agent] || []), assistantMsg],
        }));
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to send message";
        setError(message);
      } finally {
        setIsLoading(false);
      }
    },
    [activeAgent],
  );

  // ── Live board-event stream for the most recent assistant turn ─────
  // Subscribe to /api/runs/{run_id}/events for the latest assistant
  // message with a run_id. As task.* events land, fold them into the
  // last assistant message's `dispatches` map for inline rendering.
  const latestRunId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant" && messages[i].run_id) {
        return messages[i].run_id;
      }
    }
    return undefined;
  }, [messages]);

  const dispatches = useChatRunStream({
    runId: latestRunId,
    baseUrl: API_BASE,
    getIdToken,
  });

  // ── User-scoped background activity (heartbeat-driven runs) ───────
  // Persistent SSE that collects task.* events from any run — powers the
  // BoardSummaryCard's phase counts + per-agent expanders.
  const backgroundState = useUserEvents({
    baseUrl: API_BASE,
    getIdToken,
  });

  // ── Delegation binary-stream animation ────────────────────────────
  // When a task.delegated event lands in `dispatches` (i.e. the
  // orchestrator just created a board task this turn), fire a burst of
  // 0/1 glyphs from the turn bubble to the BoardSummaryCard so the
  // user SEES the delegation happen. Ref wires below.
  const boardCardRef = useRef<HTMLDivElement | null>(null);
  const lastMessageRef = useRef<HTMLDivElement | null>(null);
  const delegationStream = useDelegationStream();
  const firedDelegations = useRef<Set<string>>(new Set());

  useEffect(() => {
    for (const block of Object.values(dispatches)) {
      // One burst per task_id — if a task's created_at updates later
      // (e.g. server-side retry) we include it in the dedup key so a
      // fresh delegation re-fires the animation.
      const key = `${block.task_id}:${block.created_at}`;
      if (firedDelegations.current.has(key)) continue;
      firedDelegations.current.add(key);
      // Defer one frame so layout has the latest bubble in place.
      requestAnimationFrame(() => {
        delegationStream.fire({
          sourceEl: lastMessageRef.current,
          targetEl: boardCardRef.current,
          priority: block.priority,
        });
      });
    }
  }, [dispatches, delegationStream]);

  // Derived stats
  const turnCount = messages.filter((m) => m.role === "user").length;
  const lastToolCalls = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant" && messages[i].tool_calls) {
        return messages[i].tool_calls ?? [];
      }
    }
    return [];
  }, [messages]);

  const brief = activeEntry?.description?.slice(0, 160) ?? null;

  return (
    <div className="flex h-full min-h-0 bg-ink-900">
      {/* ── Main transcript column ───────────────────────────────── */}
      <section className="flex flex-1 min-w-0 flex-col">
        {/* Page header */}
        <header className="hairline-b px-6 pt-6 pb-4 flex items-end justify-between gap-4">
          <div>
            <div className="label-caps mb-1.5">§ 01 · CHANNEL</div>
            <h1 className="font-display text-[28px] leading-none italic">
              A conversation with{" "}
              <span className="not-italic text-signal">
                {activeEntry?.display_name || activeAgent}
              </span>
            </h1>
            <p
              className="mt-2 font-mono text-[10px] uppercase tracking-[0.16em] text-paper-40"
              suppressHydrationWarning
            >
              {headerDatestamp || "\u00A0"}
            </p>
          </div>
          <button
            type="button"
            onClick={handleNewConversation}
            disabled={isLoading}
            className="btn-hair"
            title="Start a fresh session (preserves prior transcripts on the server)"
          >
            + New Channel
          </button>
          {sessionId && (
            <a
              href={`/admin/live?session=${encodeURIComponent(sessionId)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-hair"
              title="Open the live cockpit for this session — turn timeline, tokens, cost"
            >
              LIVE →
            </a>
          )}
        </header>

        {/* Transcript */}
        <MessageList
          messages={messages}
          activeAgent={activeAgent}
          loading={isLoading}
          dispatchesByRunId={{ [latestRunId || ""]: dispatches }}
          lastMessageRef={lastMessageRef}
        />

        {error && (
          <div className="mx-6 mb-3 border border-alert-dim bg-alert/5 px-3 py-2">
            <p className="font-mono text-[11px] uppercase tracking-wider text-alert">
              ERROR ·{" "}
              <span className="normal-case tracking-normal">{error}</span>
            </p>
          </div>
        )}

        {/* Board summary — always visible, live from the SSE stream.
            Expandable per-phase (running/queued/done/failed); each
            expander shows per-agent groupings + recent task titles.
            Also serves as the landing zone for the DelegationStream
            0/1 animation fired when the orchestrator delegates. */}
        <BoardSummaryCard
          ref={boardCardRef}
          items={backgroundState.items}
          inFlight={backgroundState.inFlight}
          queued={backgroundState.queued}
        />

        {/* Mount the delegation-stream overlay at the section root so
            particles sit above everything else but below modals. */}
        <DelegationStreamOverlay state={delegationStream.state} />

        {/* Input bar */}
        <div className="hairline-t">
          <div className="mx-auto max-w-[760px] flex items-center gap-3 px-6 pt-3">
            <VoiceControls />
            <span className="font-mono text-[10px] uppercase tracking-widest text-paper-40 ml-auto">
              {isLoading ? "AWAITING REPLY" : "READY"}
            </span>
          </div>
          <MessageInput onSend={handleSend} disabled={isLoading} />
        </div>
      </section>

      {/* ── Metadata rail ────────────────────────────────────────── */}
      <aside className="hidden lg:flex w-[320px] shrink-0 flex-col hairline-l overflow-y-auto bg-ink-900">
        <div className="px-5 py-6 space-y-6">
          {/* SESSION */}
          <section>
            <div className="label-caps mb-2">§ SESSION</div>
            <dl className="space-y-1 font-mono text-[11px]">
              <div className="flex justify-between gap-3">
                <dt className="text-paper-40 uppercase">ID</dt>
                <dd className="text-paper-60 truncate" title={sessionId}>
                  {sessionId.slice(-12) || "—"}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-paper-40 uppercase">AGENT</dt>
                <dd className="text-paper">{activeAgent}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-paper-40 uppercase">TURNS</dt>
                <dd className="text-paper">
                  {turnCount.toString().padStart(3, "0")}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-paper-40 uppercase">STATE</dt>
                <dd className={isLoading ? "text-signal" : "text-paper-60"}>
                  {isLoading ? "LIVE" : "STANDBY"}
                </dd>
              </div>
            </dl>
          </section>

          {/* BRIEF */}
          {brief && (
            <section>
              <div className="label-caps mb-2">§ AGENT BRIEF</div>
              <p className="font-body text-[12.5px] text-paper-60 leading-relaxed">
                {brief}
                {activeEntry?.description &&
                  activeEntry.description.length > 160 &&
                  "…"}
              </p>
              {activeEntry?.model_ref && (
                <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-paper-40">
                  MODEL · {activeEntry.model_ref}
                </p>
              )}
            </section>
          )}

          {/* TOOLS */}
          <section>
            <div className="label-caps mb-2">§ TOOLS INVOKED · LAST TURN</div>
            {lastToolCalls.length === 0 ? (
              <p className="font-mono text-[11px] text-paper-40">— none —</p>
            ) : (
              <ul className="space-y-1">
                {lastToolCalls.map((tc, i) => (
                  <li
                    key={`${tc.name}-${i}`}
                    className="font-mono text-[11px] text-paper-60"
                  >
                    <span className="text-signal mr-1">◦</span>
                    {tc.name}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <div className="hairline-t" />

          {/* AGENT ROSTER */}
          <section>
            <AgentSelector
              value={activeAgent}
              onChange={handleAgentChange}
              disabled={isLoading}
              onActiveEntry={setActiveEntry}
            />
          </section>
        </div>
      </aside>
    </div>
  );
}
