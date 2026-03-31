"use client";

import { AuthGuard } from "@/components/auth-guard";
import { BoardView } from "@/components/board/board-view";

export default function BoardPage() {
  return (
    <AuthGuard>
      <div className="flex h-screen flex-col bg-slate-900 text-slate-100">
        {/* Navigation bar */}
        <nav className="flex items-center justify-between border-b border-slate-700 px-6 py-3">
          <h1 className="text-xl font-bold text-indigo-400">GClaw</h1>
          <div className="flex gap-4">
            <a
              href="/chat"
              className="text-sm font-medium text-slate-400 hover:text-slate-100"
            >
              Chat
            </a>
            <a
              href="/board"
              className="text-sm font-medium text-indigo-400"
            >
              Board
            </a>
          </div>
        </nav>

        {/* Board area fills remaining space */}
        <div className="flex-1 overflow-hidden">
          <BoardView />
        </div>
      </div>
    </AuthGuard>
  );
}
