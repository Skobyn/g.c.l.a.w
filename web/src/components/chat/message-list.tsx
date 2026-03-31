"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "@/types";

interface MessageListProps {
  messages: ChatMessage[];
}

export function MessageList({ messages }: MessageListProps) {
  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-slate-400">
        <p>Start a conversation with GClaw</p>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`flex ${
            msg.role === "user" ? "justify-end" : "justify-start"
          }`}
        >
          <div
            className={`max-w-[80%] rounded-lg px-4 py-2 ${
              msg.role === "user"
                ? "bg-indigo-600 text-white"
                : "bg-slate-800 text-slate-100"
            }`}
          >
            {msg.role === "assistant" ? (
              <div className="prose prose-invert prose-sm max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {msg.content}
                </ReactMarkdown>
              </div>
            ) : (
              <p>{msg.content}</p>
            )}
            {msg.tool_calls && msg.tool_calls.length > 0 && (
              <div className="mt-2 border-t border-slate-600 pt-2">
                <p className="text-xs text-slate-400">
                  Tools used: {msg.tool_calls.map((tc) => tc.name).join(", ")}
                </p>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
