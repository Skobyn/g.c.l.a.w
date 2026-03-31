"use client";

import { useState } from "react";
import { AuthGuard } from "@/components/auth-guard";
import { MemorySearch } from "@/components/memory/memory-search";
import { MemoryList } from "@/components/memory/memory-list";

type Tab = "search" | "browse";

function MemoryExplorerContent() {
  const [activeTab, setActiveTab] = useState<Tab>("search");

  return (
    <div className="flex h-screen flex-col bg-slate-900 text-slate-100">
      {/* Header */}
      <header className="border-b border-slate-700 px-6 py-4">
        <h1 className="text-2xl font-bold text-slate-100">Memory Explorer</h1>
        <p className="text-sm text-slate-400 mt-0.5">Search and browse agent memories</p>
      </header>

      {/* Tabs */}
      <div className="flex border-b border-slate-700 px-6">
        <button
          onClick={() => setActiveTab("search")}
          className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "search"
              ? "border-indigo-400 text-indigo-400"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Search
        </button>
        <button
          onClick={() => setActiveTab("browse")}
          className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
            activeTab === "browse"
              ? "border-indigo-400 text-indigo-400"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          Browse
        </button>
      </div>

      {/* Tab content */}
      <main className="flex-1 overflow-y-auto p-6">
        {activeTab === "search" ? <MemorySearch /> : <MemoryList />}
      </main>
    </div>
  );
}

export default function MemoryPage() {
  return (
    <AuthGuard>
      <MemoryExplorerContent />
    </AuthGuard>
  );
}
