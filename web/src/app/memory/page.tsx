"use client";

import { useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { MemorySearch } from "@/components/memory/memory-search";
import { MemoryList } from "@/components/memory/memory-list";

type Tab = "search" | "browse";

function MemoryExplorerContent() {
  const [activeTab, setActiveTab] = useState<Tab>("search");

  return (
    <div className="flex h-full flex-col bg-ink-900 text-paper">
      <header className="hairline-b px-8 pt-6 pb-5">
        <div className="label-caps mb-1.5">§ 04 · RECOLLECTION</div>
        <h1 className="font-display text-[30px] italic leading-none">
          Memory Explorer
        </h1>
        <p className="mt-2 font-body text-[13px] text-paper-60">
          Search and browse what the agents remember.
        </p>
      </header>

      <div className="flex hairline-b px-8 gap-6">
        {(["search", "browse"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`relative py-3 font-mono text-[11px] uppercase tracking-[0.16em] transition-colors ${
              activeTab === tab
                ? "text-signal"
                : "text-paper-60 hover:text-paper"
            }`}
          >
            {activeTab === tab && (
              <span className="absolute left-0 right-0 -bottom-px h-[2px] bg-signal" />
            )}
            {tab}
          </button>
        ))}
      </div>

      <main className="flex-1 overflow-y-auto px-8 py-6">
        {activeTab === "search" ? <MemorySearch /> : <MemoryList />}
      </main>
    </div>
  );
}

export default function MemoryPage() {
  return (
    <AppShell>
      <MemoryExplorerContent />
    </AppShell>
  );
}
