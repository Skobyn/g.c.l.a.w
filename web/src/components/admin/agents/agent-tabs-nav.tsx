"use client";

export type TabId =
  | "overview"
  | "identity"
  | "model"
  | "tools"
  | "skills"
  | "subagents"
  | "heartbeat"
  | "instructions"
  | "soul";

interface TabDef {
  id: TabId;
  label: string;
}

const TABS: TabDef[] = [
  { id: "overview", label: "Overview" },
  { id: "identity", label: "Identity" },
  { id: "model", label: "Model" },
  { id: "tools", label: "Tools" },
  { id: "skills", label: "Skills" },
  { id: "subagents", label: "Subagents" },
  { id: "heartbeat", label: "Heartbeat" },
  { id: "instructions", label: "Instructions" },
  { id: "soul", label: "Soul" },
];

export function AgentTabsNav({
  active,
  onChange,
  dirtyTabs,
}: {
  active: TabId;
  onChange: (id: TabId) => void;
  dirtyTabs: Set<TabId>;
}) {
  return (
    <nav className="sticky top-0 flex flex-col gap-0.5 p-3">
      {TABS.map((t) => {
        const isActive = t.id === active;
        const dirty = dirtyTabs.has(t.id);
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => onChange(t.id)}
            className={`flex items-center justify-between rounded-md px-3 py-2 text-left text-sm transition-colors ${
              isActive
                ? "bg-indigo-600/20 text-indigo-300"
                : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"
            }`}
          >
            <span>{t.label}</span>
            {dirty && (
              <span
                className="h-1.5 w-1.5 rounded-full bg-amber-400"
                title="Unsaved changes"
              />
            )}
          </button>
        );
      })}
    </nav>
  );
}
