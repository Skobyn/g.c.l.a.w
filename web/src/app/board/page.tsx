"use client";

import { AppShell } from "@/components/layout/app-shell";
import { BoardView } from "@/components/board/board-view";

export default function BoardPage() {
  return (
    <AppShell>
      <div className="flex h-screen flex-col bg-slate-900 text-slate-100">
        <div className="flex-1 overflow-hidden">
          <BoardView />
        </div>
      </div>
    </AppShell>
  );
}
