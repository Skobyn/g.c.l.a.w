"use client";

/**
 * Live agent-run subscription — mirrors the Firestore doc at
 * `/users/{uid}/agent_runs/{runId}` that the backend's
 * LiveSpanProcessor writes on every agent-span end.
 *
 * Returns `null` while loading, `{}` when the doc doesn't exist yet,
 * and the latest merged payload otherwise. Re-renders on every
 * Firestore onSnapshot change (~100-300 ms end-to-end).
 */

import { useEffect, useState } from "react";
import { doc, onSnapshot } from "firebase/firestore";
import { db, firebaseConfigured } from "@/lib/firebase";

export interface AgentRunDoc {
  run_id?: string;
  user_id?: string;
  active_agent?: string;
  model_id?: string;
  provider?: string;
  tokens?: {
    in?: number | null;
    out?: number | null;
    total?: number | null;
    cache_read?: number | null;
  };
  context_window?: {
    used?: number;
    max?: number;
    pct?: number;
  };
  cost_usd_session?: number;
  cost_usd_turn?: number;
  status?: string;
  tool_in_flight?: {
    name?: string;
    tool_call_id?: string;
  };
  last_span_id?: string;
  last_trace_id?: string;
  updated_at?: string;
}

export function useRunDoc(
  uid: string | null | undefined,
  runId: string | null | undefined,
): AgentRunDoc | null {
  const [data, setData] = useState<AgentRunDoc | null>(null);

  useEffect(() => {
    if (!uid || !runId || !firebaseConfigured) {
      setData(null);
      return;
    }
    const ref = doc(db, "users", uid, "agent_runs", runId);
    const unsub = onSnapshot(
      ref,
      (snap) => {
        setData((snap.exists() ? (snap.data() as AgentRunDoc) : {}) ?? {});
      },
      () => {
        // Permission / transport error — leave previous data in place
        // and log; auth-context handles user-visible error surfacing.
      },
    );
    return () => unsub();
  }, [uid, runId]);

  return data;
}
