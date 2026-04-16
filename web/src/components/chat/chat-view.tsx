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

/** Per-browser-session base session ID. Individual agents derive
 *  their scoped id from this. Backend further suffixes non-default
 *  agents with "::<agent>" — this base is shared across all agents
 *  so the user can see them as one coherent conversation scope. */
function getBaseSessionId(): string {
  const key = "gclaw_session_id";
  let sessionId = sessionStorage.getItem(key);
  if (!sessionId) {
    sessionId = `sess_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    sessionStorage.setItem(key, sessionId);
  }
  return sessionId;
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

  const handleAgentChange = useCallback((name: string) => {
    setActiveAgent(name);
    setError(null);
  }, []);

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
        <AgentSelector
          value={activeAgent}
          onChange={handleAgentChange}
          disabled={isLoading}
        />
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
