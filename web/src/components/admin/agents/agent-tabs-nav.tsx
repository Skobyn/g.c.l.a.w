"use client";

/**
 * Agent detail tabs — left-column table of contents, numbered in Roman.
 */

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
  numeral: string;
}

const TABS: TabDef[] = [
  { id: "overview", label: "Overview", numeral: "I" },
  { id: "identity", label: "Identity", numeral: "II" },
  { id: "model", label: "Model", numeral: "III" },
  { id: "tools", label: "Tools", numeral: "IV" },
  { id: "skills", label: "Skills", numeral: "V" },
  { id: "subagents", label: "Subagents", numeral: "VI" },
  { id: "heartbeat", label: "Heartbeat", numeral: "VII" },
  { id: "instructions", label: "Instructions", numeral: "VIII" },
  { id: "soul", label: "Soul", numeral: "IX" },
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
    <nav className="sticky top-0 flex flex-col p-4">
      <div className="label-caps pb-2 hairline-b mb-2">§ CONTENTS</div>
      {TABS.map((t) => {
        const isActive = t.id === active;
        const dirty = dirtyTabs.has(t.id);
        return (
          <button
            key={t.id}
            type="button"
            onClick={() => onChange(t.id)}
            className={`group relative grid grid-cols-[32px_1fr_auto] items-baseline gap-2 py-2.5 pl-2 pr-2 text-left transition-colors hairline-b ${
              isActive
                ? "text-signal"
                : "text-paper-60 hover:text-paper"
            }`}
          >
            {isActive && (
              <span className="absolute left-0 top-2.5 bottom-2.5 w-[2px] bg-signal" />
            )}
            <span
              className={`font-mono text-[10px] ${
                isActive ? "text-signal" : "text-paper-40"
              }`}
            >
              {t.numeral}.
            </span>
            <span
              className={`font-display italic text-[14px] ${
                isActive ? "text-signal" : ""
              }`}
            >
              {t.label}
            </span>
            {dirty && (
              <span
                className="h-1.5 w-1.5 rounded-full bg-gold"
                title="Unsaved changes"
              />
            )}
          </button>
        );
      })}
    </nav>
  );
}
