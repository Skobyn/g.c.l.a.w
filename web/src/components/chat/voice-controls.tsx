"use client";

/**
 * Voice toggle button and status indicator for the chat view.
 *
 * Shows a microphone button that starts/stops the voice session.
 * Visual states: idle (gray), connecting (yellow pulse), listening (green pulse),
 * processing (blue), error (red).
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { useAuth } from "@/contexts/auth-context";
import { VoiceClient, type VoiceStateCallback } from "@/lib/voice-client";
import type { VoiceState } from "@/types";

const STATE_STYLES: Record<VoiceState, string> = {
  idle: "bg-slate-600 hover:bg-slate-500",
  connecting: "bg-yellow-600 animate-pulse",
  listening: "bg-green-600 animate-pulse",
  processing: "bg-blue-600",
  error: "bg-red-600",
};

const STATE_LABELS: Record<VoiceState, string> = {
  idle: "Start voice",
  connecting: "Connecting...",
  listening: "Listening...",
  processing: "Speaking...",
  error: "Error — tap to retry",
};

export function VoiceControls() {
  const { getIdToken } = useAuth();
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const clientRef = useRef<VoiceClient | null>(null);

  useEffect(() => {
    return () => {
      clientRef.current?.stop();
    };
  }, []);

  const toggle = useCallback(async () => {
    if (voiceState === "idle" || voiceState === "error") {
      const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
      const onStateChange: VoiceStateCallback = (s) => setVoiceState(s);
      const client = new VoiceClient(baseUrl, getIdToken, onStateChange);
      clientRef.current = client;
      await client.start();
    } else {
      clientRef.current?.stop();
      clientRef.current = null;
    }
  }, [voiceState, getIdToken]);

  return (
    <button
      onClick={toggle}
      className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-white transition-colors ${STATE_STYLES[voiceState]}`}
      title={STATE_LABELS[voiceState]}
    >
      {/* Microphone icon (inline SVG) */}
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 1a4 4 0 00-4 4v6a4 4 0 008 0V5a4 4 0 00-4-4z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M19 10v1a7 7 0 01-14 0v-1M12 19v4M8 23h8" />
      </svg>
      <span className="hidden sm:inline">{STATE_LABELS[voiceState]}</span>
    </button>
  );
}
