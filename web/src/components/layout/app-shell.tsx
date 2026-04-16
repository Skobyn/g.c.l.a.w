"use client";

import { useEffect, useState } from "react";
import { AuthGuard } from "@/components/auth-guard";
import { Sidebar } from "@/components/layout/sidebar";
import { formatTickerStamp } from "@/lib/format";

interface AppShellProps {
  children: React.ReactNode;
}

/**
 * Ticker bar across the top of every page.
 *
 * Left: dateline in mono (ticks every 15s).
 * Middle: rotating flavor text.
 * Right: status pill (ALL AGENTS NOMINAL).
 */
function TickerBar() {
  const [stamp, setStamp] = useState(() => formatTickerStamp());

  useEffect(() => {
    const handle = setInterval(() => setStamp(formatTickerStamp()), 15_000);
    return () => clearInterval(handle);
  }, []);

  return (
    <div className="sticky top-0 z-20 h-7 flex items-center justify-between gap-4 bg-ink-900 hairline-b px-4 font-mono text-[10px] uppercase tracking-[0.18em] text-paper-60">
      <div className="flex items-center gap-3 min-w-0">
        <span className="text-paper">{stamp}</span>
        <span className="text-paper-40">·</span>
        <span className="hidden md:inline truncate">
          SIGNAL NOMINAL · CHANNELS OPEN
        </span>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span className="phosphor-dot" />
        <span className="text-signal">ALL AGENTS NOMINAL</span>
      </div>
    </div>
  );
}

/**
 * AppShell wraps AuthGuard + Sidebar + ticker + scrollable main.
 */
export function AppShell({ children }: AppShellProps) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <AuthGuard>
      <div className="flex min-h-screen bg-ink-900 text-paper">
        <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />
        <div
          className={`flex-1 min-w-0 flex flex-col transition-[margin] duration-200 ${
            collapsed ? "ml-[60px]" : "ml-[224px]"
          }`}
        >
          <TickerBar />
          <main className="flex-1 min-w-0 overflow-y-auto">{children}</main>
        </div>
      </div>
    </AuthGuard>
  );
}
