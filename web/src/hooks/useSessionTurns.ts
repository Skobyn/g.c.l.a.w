"use client";

/**
 * Live turn-by-turn subscription for a chat session.
 *
 * Subscribes to ``/users/{uid}/agent_runs/{sessionId}/turns`` via
 * onSnapshot, returning each turn's doc sorted newest-first. Each
 * doc reflects the live state of that turn as spans end — tokens
 * accumulate in-place, status progresses.
 *
 * Used by the /admin/live page (session mode) to render a timeline
 * of turns within a chat session, plus a session-level rollup
 * (total tokens, total cost, total turns) computed client-side by
 * summing across the list.
 */

import { useEffect, useMemo, useState } from "react";
import {
  collection,
  onSnapshot,
  orderBy,
  query,
} from "firebase/firestore";
import { db, firebaseConfigured } from "@/lib/firebase";
import type { AgentRunDoc } from "@/hooks/useRunDoc";

export interface TurnDoc extends AgentRunDoc {
  turn_id?: string;
  started_at?: string;
}

export interface SessionRollup {
  turns: TurnDoc[];
  loaded: boolean;
  totals: {
    turn_count: number;
    tokens_in: number;
    tokens_out: number;
    tokens_cache_read: number;
    cost_usd: number;
  };
}

function sumTokens(turns: TurnDoc[], key: "in" | "out" | "cache_read"): number {
  let t = 0;
  for (const turn of turns) {
    const v = turn.tokens?.[key];
    if (typeof v === "number") t += v;
  }
  return t;
}

function sumCost(turns: TurnDoc[]): number {
  let c = 0;
  for (const turn of turns) {
    const v = turn.cost_usd_session ?? turn.cost_usd_turn;
    if (typeof v === "number") c += v;
  }
  return c;
}

export function useSessionTurns(
  uid: string | null | undefined,
  sessionId: string | null | undefined,
): SessionRollup {
  const [turns, setTurns] = useState<TurnDoc[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!uid || !sessionId || !firebaseConfigured) {
      setTurns([]);
      setLoaded(false);
      return;
    }
    const col = collection(
      db,
      "users",
      uid,
      "agent_runs",
      sessionId,
      "turns",
    );
    // Sort by started_at desc; Firestore returns docs in the indexed
    // order. Falls back to client-side sort below.
    const q = query(col, orderBy("started_at", "desc"));
    const unsub = onSnapshot(
      q,
      (snap) => {
        const rows: TurnDoc[] = snap.docs.map((d) => {
          const raw = d.data() as Record<string, unknown>;
          return {
            ...(raw as AgentRunDoc),
            turn_id: (raw.turn_id as string) ?? d.id,
            started_at: raw.started_at as string | undefined,
          };
        });
        rows.sort((a, b) =>
          (b.started_at ?? b.updated_at ?? "").localeCompare(
            a.started_at ?? a.updated_at ?? "",
          ),
        );
        setTurns(rows);
        setLoaded(true);
      },
      () => {
        // Firestore error — treat as loaded with empty list so the UI
        // can surface its own "no turns yet" state.
        setLoaded(true);
      },
    );
    return () => {
      unsub();
    };
  }, [uid, sessionId]);

  const totals = useMemo(
    () => ({
      turn_count: turns.length,
      tokens_in: sumTokens(turns, "in"),
      tokens_out: sumTokens(turns, "out"),
      tokens_cache_read: sumTokens(turns, "cache_read"),
      cost_usd: sumCost(turns),
    }),
    [turns],
  );

  return { turns, loaded, totals };
}
