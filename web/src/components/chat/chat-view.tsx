"use client";

/**
 * Main chat interface component.
 *
 * Manages conversation state, calls the API client for each message,
 * and renders the message list with input.
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { useAuth } from "@/contexts/auth-context";
import { createApiClient } from "@/lib/api-client";
import { MessageList } from "./message-list";
import { MessageInput } from "./message-input";
import { VoiceControls } from "./voice-controls";
import type { ChatMessage } from "@/types";

/** Generate a simple unique ID for messages. */
function msgId(): string {
  return `msg_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

/** Generate a session ID (persisted for the browser session). */
function getSessionId(): string {
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
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const clientRef = useRef(createApiClient(getIdToken));

  // Keep client in sync with getIdToken
  useEffect(() => {
    clientRef.current = createApiClient(getIdToken);
  }, [getIdToken]);

  const handleSend = useCallback(
    async (content: string) => {
      // Add user message immediately
      const userMsg: ChatMessage = {
        id: msgId(),
        role: "user",
        content,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);
      setError(null);

      try {
        const sessionId = getSessionId();
        const response = await clientRef.current.chat(sessionId, content);

        const assistantMsg: ChatMessage = {
          id: msgId(),
          role: "assistant",
          content: response.text,
          timestamp: new Date(),
          tool_calls: response.tool_calls,
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to send message";
        setError(message);
      } finally {
        setIsLoading(false);
      }
    },
    [getIdToken]
  );

  return (
    <div className="flex h-full flex-col">
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
