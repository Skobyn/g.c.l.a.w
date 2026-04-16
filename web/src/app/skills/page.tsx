"use client";

import { useState, useEffect, useCallback } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { SkillCard } from "@/components/skills/skill-card";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";
import type { SkillInfo } from "@/types";

function SkillsContent() {
  const { getIdToken } = useAuth();
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const fetchSkills = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const api = createApiClient(getIdToken);
      const data = await api.getSkills();
      setSkills(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load skills");
    } finally {
      setLoading(false);
    }
  }, [getIdToken]);

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  const filtered = filter
    ? skills.filter(
        (s) =>
          s.name.toLowerCase().includes(filter.toLowerCase()) ||
          s.description.toLowerCase().includes(filter.toLowerCase())
      )
    : skills;

  return (
    <div className="flex h-full flex-col bg-ink-900 text-paper">
      <header className="hairline-b px-8 pt-6 pb-5">
        <div className="flex items-end justify-between">
          <div>
            <div className="label-caps mb-1.5">§ 06 · PLAYBOOKS</div>
            <h1 className="font-display text-[30px] italic leading-none">Skills</h1>
            <p className="mt-2 font-body text-[13px] text-paper-60">
              {skills.length} skill{skills.length !== 1 ? "s" : ""} installed · agent-runnable playbooks
            </p>
          </div>
          <button
            onClick={fetchSkills}
            disabled={loading}
            className="btn-hair"
          >
            {loading ? "REFRESHING…" : "REFRESH"}
          </button>
        </div>
        <div className="mt-4 max-w-md">
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter skills…"
            className="input-hair"
          />
        </div>
      </header>

      <main className="flex-1 overflow-y-auto px-8 py-6">
        {error && (
          <div className="mb-4 border border-alert-dim bg-alert/5 px-4 py-2.5 font-mono text-[11px] uppercase tracking-wider text-alert">
            {error}
          </div>
        )}

        {loading && skills.length === 0 ? (
          <div className="flex items-center justify-center py-24">
            <p className="font-mono text-[11px] uppercase tracking-widest text-paper-40">
              LOADING<span className="signal-cursor" />
            </p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="py-16 text-center font-mono text-[11px] uppercase tracking-widest text-paper-40">
            {filter ? "— NO MATCH —" : "— NO SKILLS REGISTERED —"}
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((skill) => (
              <SkillCard key={skill.name} skill={skill} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

export default function SkillsPage() {
  return (
    <AppShell>
      <SkillsContent />
    </AppShell>
  );
}
