"use client";

import type { RefObject } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage, DispatchBlock } from "@/types";
import { formatTimestamp } from "@/lib/format";
import { DispatchBlockView } from "./dispatch-block";

interface MessageListProps {
  messages: ChatMessage[];
  activeAgent: string;
  loading?: boolean;
  /** Live board-task dispatch blocks keyed by run_id → (task_id → block). */
  dispatchesByRunId?: Record<string, Record<string, DispatchBlock>>;
  /** Ref written to the most recent assistant turn — used as the
   *  source element for the delegation-stream binary animation. */
  lastMessageRef?: RefObject<HTMLDivElement | null>;
}

/**
 * Transcript, editorial style.
 *
 * Each turn is a typeset entry with a margin dateline in mono; user turns
 * are indented and greyed, agent turns ride a hairline signal-green rule.
 */
export function MessageList({
  messages,
  activeAgent,
  loading,
  dispatchesByRunId,
  lastMessageRef,
}: MessageListProps) {
  // Find the index of the last assistant message so we can wire the
  // ref exactly once.
  let lastAssistantIdx = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "assistant") {
      lastAssistantIdx = i;
      break;
    }
  }
  if (messages.length === 0 && !loading) {
    return (
      <div className="flex flex-1 items-center justify-center px-6">
        <div className="max-w-md text-center">
          <p className="label-caps mb-3">EMPTY CHANNEL</p>
          <h2 className="font-display text-2xl italic text-paper-60">
            The line is open.
          </h2>
          <p className="mt-3 text-sm text-paper-40">
            Say something to <span className="text-paper">{activeAgent}</span> and this
            transcript will begin.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <div className="mx-auto w-full max-w-[760px] px-6 py-8 space-y-7">
        {messages.map((msg, idx) => {
          const stamp = formatTimestamp(msg.timestamp);
          const isUser = msg.role === "user";
          const isLastAssistant = idx === lastAssistantIdx;
          return (
            <div
              key={msg.id}
              className="group"
              ref={
                isLastAssistant && lastMessageRef
                  ? (el) => {
                      // Unified ref forwarding — React 19 accepts either
                      // a RefObject or a callback. Write through when
                      // mounted/unmounted to keep stream source accurate.
                      (lastMessageRef as { current: HTMLDivElement | null }).current =
                        el;
                    }
                  : undefined
              }
            >
              {/* Meta line */}
              <div className="flex items-baseline gap-3 mb-1.5">
                <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-paper-40">
                  {stamp}
                </span>
                <span
                  className={`font-mono text-[10px] uppercase tracking-[0.18em] ${
                    isUser ? "text-paper-40" : "text-signal"
                  }`}
                >
                  {isUser ? "SBENS" : activeAgent}
                </span>
              </div>

              {/* Body */}
              {isUser ? (
                <div className="pl-6 text-paper-60 font-body text-[14.5px] leading-[1.65]">
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                </div>
              ) : (
                <div className="pl-4 border-l border-signal-dim/60">
                  <div className="prose-phosphor">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                  {(() => {
                    const blocks = msg.run_id
                      ? dispatchesByRunId?.[msg.run_id] ?? {}
                      : {};
                    const taskIds = Object.keys(blocks);
                    return taskIds.map((tid) => (
                      <DispatchBlockView key={tid} block={blocks[tid]} />
                    ));
                  })()}
                  {msg.tool_calls && msg.tool_calls.length > 0 && (
                    <div className="mt-3 hairline-t pt-2">
                      <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-paper-40">
                        TOOLS ·{" "}
                        <span className="text-paper-60 normal-case">
                          {msg.tool_calls.map((tc) => tc.name).join(", ")}
                        </span>
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {loading && (
          <div className="pl-4 border-l border-signal-dim/60">
            <span className="label-caps-signal">TRANSMITTING</span>
            <span className="signal-cursor" />
          </div>
        )}
      </div>
    </div>
  );
}
