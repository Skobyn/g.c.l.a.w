"use client";

import { AppShell } from "@/components/layout/app-shell";
import { ChatView } from "@/components/chat/chat-view";

export default function ChatPage() {
  return (
    <AppShell>
      <div className="flex h-screen flex-col bg-slate-900 text-slate-100">
        <div className="flex-1 overflow-hidden">
          <ChatView />
        </div>
      </div>
    </AppShell>
  );
}
