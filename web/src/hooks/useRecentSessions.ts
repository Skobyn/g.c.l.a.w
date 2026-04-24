"use client";

/**
 * Live subscription to the user's recent agent_runs (chat sessions).
 *
 * Each agent_runs/{run_id} doc carries a rolling snapshot of the
 * session's last activity (active_agent, model_id, status,
 * updated_at). This hook returns the most-recent N sessions sorted
 * by updated_at desc, so the Observability page can show "click a
 * recent session to inspect its turns and transcripts."
 */

import { useEffect, useState } from "react";
import {
  collection,
  limit as fbLimit,
  onSnapshot,
  orderBy,
  query,
} from "firebase/firestore";
import { db, firebaseConfigured } from "@/lib/firebase";

export interface RecentSession {
  id: string;
  active_agent?: string;
  model_id?: string;
  status?: string;
  updated_at?: string;
}

export function useRecentSessions(
  uid: string | null | undefined,
  limit: number = 10,
): { sessions: RecentSession[]; loaded: boolean } {
  const [sessions, setSessions] = useState<RecentSession[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!uid || !firebaseConfigured) {
      setSessions([]);
      setLoaded(false);
      return;
    }
    const col = collection(db, "users", uid, "agent_runs");
    const q = query(col, orderBy("updated_at", "desc"), fbLimit(limit));
    const unsub = onSnapshot(
      q,
      (snap) => {
        const rows: RecentSession[] = snap.docs.map((d) => {
          const raw = d.data() as Record<string, unknown>;
          return {
            id: d.id,
            active_agent: raw.active_agent as string | undefined,
            model_id: raw.model_id as string | undefined,
            status: raw.status as string | undefined,
            updated_at: raw.updated_at as string | undefined,
          };
        });
        setSessions(rows);
        setLoaded(true);
      },
      () => setLoaded(true),
    );
    return () => unsub();
  }, [uid, limit]);

  return { sessions, loaded };
}
