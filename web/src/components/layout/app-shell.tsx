"use client";

import { useState } from "react";
import { AuthGuard } from "@/components/auth-guard";
import { Sidebar } from "@/components/layout/sidebar";

interface AppShellProps {
  children: React.ReactNode;
}

/**
 * AppShell wraps AuthGuard + Sidebar + the main scrollable content area.
 * Sidebar collapsed state is lifted here so the main area can offset correctly.
 */
export function AppShell({ children }: AppShellProps) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <AuthGuard>
      <div className="flex min-h-screen bg-slate-950 text-slate-100">
        <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />
        {/* Main content shifts right to account for the fixed sidebar */}
        <main
          className={`flex-1 min-w-0 overflow-y-auto transition-all duration-200 ${
            collapsed ? "ml-16" : "ml-56"
          }`}
        >
          {children}
        </main>
      </div>
    </AuthGuard>
  );
}
