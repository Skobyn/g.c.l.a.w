"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { SkillCard } from "@/components/skills/skill-card";
import { SkillEditor } from "@/components/skills/skill-editor";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";
import type { SkillCreatePayload, SkillInfo } from "@/types";

function SkillsContent() {
  const { getIdToken } = useAuth();
  const api = useMemo(() => createApiClient(getIdToken), [getIdToken]);
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [editing, setEditing] = useState<SkillInfo | null>(null);
  const [creating, setCreating] = useState(false);

  const fetchSkills = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getSkills();
      setSkills(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load skills");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  const filtered = filter
    ? skills.filter(
        (s) =>
          s.name.toLowerCase().includes(filter.toLowerCase()) ||
          s.description.toLowerCase().includes(filter.toLowerCase()),
      )
    : skills;

  const existingNames = useMemo(() => skills.map((s) => s.name), [skills]);

  async function handleCreate(payload: SkillCreatePayload) {
    await api.createSkill(payload);
    setCreating(false);
    await fetchSkills();
  }

  async function handleUpdate(payload: SkillCreatePayload) {
    if (!editing) return;
    await api.updateSkill(editing.name, payload);
    setEditing(null);
    await fetchSkills();
  }

  async function handleDelete(skill: SkillInfo) {
    const warn =
      skill.source === "builtin"
        ? `"${skill.name}" is a built-in skill. Deleting it only removes the Firestore record — it will be re-seeded on the next app restart unless you also delete skills/${skill.name}/ on disk. Continue?`
        : `Delete skill "${skill.name}"?`;
    if (!confirm(warn)) return;
    try {
      await api.deleteSkill(skill.name);
      await fetchSkills();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <div className="flex h-full flex-col bg-ink-900 text-paper">
      <header className="hairline-b px-8 pt-6 pb-5">
        <div className="flex items-end justify-between">
          <div>
            <div className="label-caps mb-1.5">§ 06 · PLAYBOOKS</div>
            <h1 className="font-display text-[30px] italic leading-none">Skills</h1>
            <p className="mt-2 font-body text-[13px] text-paper-60">
              {skills.length} skill{skills.length !== 1 ? "s" : ""} registered · agent-runnable playbooks
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchSkills}
              disabled={loading}
              className="btn-hair"
            >
              {loading ? "REFRESHING…" : "REFRESH"}
            </button>
            <button
              type="button"
              onClick={() => setCreating(true)}
              className="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500"
            >
              + New skill
            </button>
          </div>
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
              <SkillCard
                key={skill.name}
                skill={skill}
                onEdit={setEditing}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </main>

      {creating && (
        <SkillEditor
          mode="create"
          initial={null}
          existingNames={existingNames}
          onClose={() => setCreating(false)}
          onSave={handleCreate}
        />
      )}
      {editing && (
        <SkillEditor
          mode="edit"
          initial={editing}
          existingNames={existingNames}
          onClose={() => setEditing(null)}
          onSave={handleUpdate}
        />
      )}
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
