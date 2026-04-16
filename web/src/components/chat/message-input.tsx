"use client";

import { useState, useCallback, type KeyboardEvent, type FormEvent } from "react";

interface MessageInputProps {
  onSend: (message: string) => void;
  disabled: boolean;
}

/**
 * Hairline input. No rounded box. Focus turns the underline signal green.
 * Enter submits. Shift+Enter for a new line.
 */
export function MessageInput({ onSend, disabled }: MessageInputProps) {
  const [input, setInput] = useState("");
  const [focused, setFocused] = useState(false);

  const handleSubmit = useCallback(
    (e?: FormEvent) => {
      e?.preventDefault();
      const trimmed = input.trim();
      if (!trimmed) return;
      onSend(trimmed);
      setInput("");
    },
    [input, onSend],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  return (
    <form onSubmit={handleSubmit} className="px-6 pb-6 pt-3">
      <div className="mx-auto max-w-[760px]">
        <div
          className={`flex items-end gap-3 border-b py-2 transition-colors ${
            focused ? "border-signal" : "border-hair-bright"
          }`}
        >
          <span
            className={`font-mono text-xs mb-2 shrink-0 ${
              focused ? "text-signal" : "text-paper-40"
            }`}
          >
            &gt;
          </span>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            onKeyDown={handleKeyDown}
            placeholder="Speak into the channel — press Enter to transmit."
            disabled={disabled}
            rows={1}
            className="flex-1 resize-none bg-transparent font-body text-[15px] text-paper placeholder:text-paper-40 placeholder:italic focus:outline-none disabled:opacity-50"
            style={{ minHeight: 28, maxHeight: 240 }}
          />
          <button
            type="submit"
            disabled={disabled || !input.trim()}
            className="btn-hair-signal shrink-0 mb-1"
          >
            Transmit
          </button>
        </div>
        <div className="mt-2 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.14em] text-paper-40">
          <span>ENTER · SEND · SHIFT+ENTER · NEWLINE</span>
          {input.length > 0 && (
            <span>{input.length.toString().padStart(4, "0")} CHARS</span>
          )}
        </div>
      </div>
    </form>
  );
}
