"use client";

/**
 * Voice toggle, phosphor-styled.
 *
 * States: idle (neutral), connecting (amber pulse), listening (signal
 * pulse), processing (signal dim), error (alert). Hairline border, small
 * caps label.
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { useAuth } from "@/contexts/auth-context";
import { VoiceClient, type VoiceStateCallback } from "@/lib/voice-client";
import type { VoiceState } from "@/types";

const STATE_LABELS: Record<VoiceState, string> = {
  idle: "OPEN LINE",
  connecting: "LINKING...",
  listening: "LISTENING",
  processing: "REPLYING",
  error: "SIGNAL LOST",
};

function VoiceIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 1a4 4 0 00-4 4v6a4 4 0 008 0V5a4 4 0 00-4-4z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 10v1a7 7 0 01-14 0v-1M12 19v4M8 23h8" />
    </svg>
  );
}

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

  const isActive = voiceState === "listening" || voiceState === "connecting";
  const isError = voiceState === "error";

  const cls = isActive
    ? "btn-hair-signal"
    : isError
      ? "btn-hair-alert"
      : "btn-hair";

  return (
    <button
      type="button"
      onClick={toggle}
      className={`${cls} flex items-center gap-2`}
      title={STATE_LABELS[voiceState]}
    >
      <VoiceIcon />
      <span>{STATE_LABELS[voiceState]}</span>
      {isActive && <span className="phosphor-dot" />}
    </button>
  );
}
