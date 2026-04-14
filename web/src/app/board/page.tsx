"use client";

import { AppShell } from "@/components/layout/app-shell";
import { BoardView } from "@/components/board/board-view";
import { BoardErrorBoundary } from "@/components/board/board-error-boundary";

export default function BoardPage() {
  return (
    <AppShell>
      <div className="flex h-screen flex-col bg-slate-900 text-slate-100">
        <div className="flex-1 overflow-hidden">
          <BoardErrorBoundary>
            <BoardView />
          </BoardErrorBoundary>
        </div>
      </div>
    </AppShell>
  );
}
