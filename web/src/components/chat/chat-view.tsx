"use client";

/**
 * Main chat interface component.
 *
 * Manages conversation state per-agent so switching between agents
 * keeps each conversation intact. Calls the API client for each
 * message, scoping the session_id per-agent on the backend.
 */

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { useAuth } from "@/contexts/auth-context";
import { createApiClient } from "@/lib/api-client";
import { MessageList } from "./message-list";
import { MessageInput } from "./message-input";
import { VoiceControls } from "./voice-controls";
import { AgentSelector, DEFAULT_AGENT } from "./agent-selector";
import type { ChatMessage } from "@/types";

/** Generate a simple unique ID for messages. */
function msgId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

/** Per-user base session ID. Individual agents derive their scoped
 *  id from this. Backend further suffixes non-default agents with
 *  "::<agent>" — this base is shared across all agents so the user
 *  can see them as one coherent conversation scope.
 *
 *  Stored in localStorage so it survives browser restart (persisting
 *  the server-side transcript reference across days). Use
 *  resetBaseSessionId() to explicitly start a new conversation. */
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
  // Per-agent message history — switching agents swaps the message list.
  const [messagesByAgent, setMessagesByAgent] = useState<
    Record<string, ChatMessage[]>
  >({});
  const [activeAgent, setActiveAgent] = useState<string>(DEFAULT_AGENT);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const clientRef = useRef(createApiClient(getIdToken));

  // Keep client in sync with getIdToken
  useEffect(() => {
    clientRef.current = createApiClient(getIdToken);
  }, [getIdToken]);

  const messages = useMemo(
    () => messagesByAgent[activeAgent] || [],
    [messagesByAgent, activeAgent],
  );

  /** Lazily fetch persisted history for an agent on first activation. */
  const loadHistory = useCallback(
    async (agent: string) => {
      if (messagesByAgent[agent] !== undefined) return; // already loaded
      try {
        const sessionId = getBaseSessionId();
        const resp = await clientRef.current.getChatHistory(
          sessionId,
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
        // History is best-effort — absent history shouldn't block chatting.
        // eslint-disable-next-line no-console
        console.warn("failed to load chat history for", agent, err);
        setMessagesByAgent((prev) =>
          prev[agent] !== undefined ? prev : { ...prev, [agent]: [] },
        );
      }
    },
    [messagesByAgent],
  );

  // Load history for the default agent on mount.
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
    resetBaseSessionId();
    setMessagesByAgent({});
    setError(null);
    // Force re-fetch (which for a fresh session_id returns [] → empty UI).
    void loadHistory(activeAgent);
  }, [activeAgent, loadHistory]);

  const handleSend = useCallback(
    async (content: string) => {
      const agent = activeAgent;

      // Add user message immediately to this agent's history.
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
        const sessionId = getBaseSessionId();
        const response = await clientRef.current.chat(
          sessionId,
          content,
          agent === DEFAULT_AGENT ? null : agent,
        );

        const assistantMsg: ChatMessage = {
          id: msgId(),
          role: "assistant",
          content: response.text,
          timestamp: new Date(),
          tool_calls: response.tool_calls,
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

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-slate-700 px-4 py-2">
        <div className="text-sm text-slate-300">
          Chatting with:{" "}
          <span className="font-medium text-slate-100">{activeAgent}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleNewConversation}
            disabled={isLoading}
            className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800 transition-colors disabled:opacity-50"
            title="Start a fresh conversation (new session id, preserves previous server-side transcript)"
          >
            New conversation
          </button>
          <AgentSelector
            value={activeAgent}
            onChange={handleAgentChange}
            disabled={isLoading}
          />
        </div>
      </div>

      <MessageList messages={messages} />

      {error && (
        <div className="mx-4 rounded-lg bg-red-900/50 px-4 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="flex items-center gap-2 px-4 pb-2">
        <VoiceControls />
        <div className="flex-1">
          <MessageInput onSend={handleSend} disabled={isLoading} />
        </div>
      </div>
    </div>
  );
}
