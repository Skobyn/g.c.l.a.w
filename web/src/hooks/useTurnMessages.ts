"use client";

/**
 * Live per-author message subscription for a single turn.
 *
 * Subscribes to ``users/{uid}/agent_runs/{sessionId}/turns/{turnId}/messages``
 * via onSnapshot. Messages are written by AgentRunner._emit_turn_messages
 * after the turn finishes — one "user" input doc + one "agent" output
 * doc per distinct author in the ADK event stream — so this hook
 * lights up post-turn rather than streaming during the turn.
 *
 * Content is server-side redacted (regex-based, see
 * gclaw.observability.redaction). Render as plaintext.
 */

import { useEffect, useState } from "react";
import { collection, onSnapshot, orderBy, query } from "firebase/firestore";
import { db, firebaseConfigured } from "@/lib/firebase";

export interface TurnMessage {
  seq: number;
  ts: string;
  author: string;
  role: "input" | "output";
  text?: string;
  tool_calls?: Array<{ name: string; args: Record<string, unknown> }>;
}

export function useTurnMessages(
  uid: string | null | undefined,
  sessionId: string | null | undefined,
  turnId: string | null | undefined,
): { messages: TurnMessage[]; loaded: boolean } {
  const [messages, setMessages] = useState<TurnMessage[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!uid || !sessionId || !turnId || !firebaseConfigured) {
      setMessages([]);
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
      turnId,
      "messages",
    );
    const q = query(col, orderBy("seq", "asc"));
    const unsub = onSnapshot(
      q,
      (snap) => {
        const rows: TurnMessage[] = snap.docs.map((d) => {
          const raw = d.data() as Record<string, unknown>;
          return {
            seq: (raw.seq as number) ?? 0,
            ts: (raw.ts as string) ?? "",
            author: (raw.author as string) ?? "unknown",
            role: ((raw.role as string) ?? "output") as "input" | "output",
            text: raw.text as string | undefined,
            tool_calls: raw.tool_calls as TurnMessage["tool_calls"] | undefined,
          };
        });
        setMessages(rows);
        setLoaded(true);
      },
      () => setLoaded(true),
    );
    return () => unsub();
  }, [uid, sessionId, turnId]);

  return { messages, loaded };
}
