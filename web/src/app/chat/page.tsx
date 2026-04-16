"use client";

import { AppShell } from "@/components/layout/app-shell";
import { ChatView } from "@/components/chat/chat-view";

export default function ChatPage() {
  return (
    <AppShell>
      <div className="flex h-[calc(100vh-28px)] flex-col bg-ink-900 text-paper">
        <div className="flex-1 overflow-hidden">
          <ChatView />
        </div>
      </div>
    </AppShell>
  );
}
