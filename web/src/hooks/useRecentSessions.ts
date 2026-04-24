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
import { collection, onSnapshot, query } from "firebase/firestore";
import { db, firebaseConfigured } from "@/lib/firebase";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";

const API_POLL_MS = 5_000;

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
  const { getIdToken } = useAuth();

  useEffect(() => {
    // API fallback for builds without Firebase client config (e.g.
    // NEXT_PUBLIC_DEV_BYPASS_AUTH=true). Polls /admin/agent-runs
    // every 5s — backend is single-user, so the noise is bounded.
    if (!firebaseConfigured) {
      // Use real auth token resolver from context — passing
      // `async () => null` would make the api-client throw
      // "Not authenticated" before the fetch ever leaves, which is
      // exactly the silent-empty failure mode this panel kept hitting.
      const api = createApiClient(getIdToken);
      let cancelled = false;
      const fetchOnce = async () => {
        try {
          const { sessions } = await api.listAgentRuns({ limit });
          if (!cancelled) {
            setSessions(sessions);
            setLoaded(true);
          }
        } catch {
          if (!cancelled) {
            setSessions([]);
            setLoaded(true);
          }
        }
      };
      void fetchOnce();
      const id = setInterval(fetchOnce, API_POLL_MS);
      return () => {
        cancelled = true;
        clearInterval(id);
      };
    }
    if (!uid) {
      setSessions([]);
      setLoaded(false);
      return;
    }
    const col = collection(db, "users", uid, "agent_runs");
    // No orderBy — older docs may not have `updated_at` and Firestore
    // would filter them out, leaving the snapshot listener silent in
    // a "no docs match" path that mimics a hang. Client-side sort
    // below handles ordering + the limit cap.
    const q = query(col);
    const unsub = onSnapshot(
      q,
      (snap) => {
        const rows: RecentSession[] = snap.docs.map((d) => {
          const raw = d.data() as Record<string, unknown>;
          const ts = raw.updated_at;
          return {
            id: d.id,
            active_agent: raw.active_agent as string | undefined,
            model_id: raw.model_id as string | undefined,
            status: raw.status as string | undefined,
            updated_at:
              typeof ts === "string"
                ? ts
                : ts && typeof (ts as { toDate?: () => Date }).toDate === "function"
                  ? (ts as { toDate: () => Date }).toDate().toISOString()
                  : undefined,
          };
        });
        rows.sort((a, b) =>
          (b.updated_at ?? "").localeCompare(a.updated_at ?? ""),
        );
        setSessions(rows.slice(0, limit));
        setLoaded(true);
      },
      () => {
        // Permission denied / index missing — render empty state
        // rather than hang the panel.
        setSessions([]);
        setLoaded(true);
      },
    );
    return () => unsub();
  }, [uid, limit, getIdToken]);

  return { sessions, loaded };
}
