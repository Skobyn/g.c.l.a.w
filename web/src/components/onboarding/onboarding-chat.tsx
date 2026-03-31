"use client";

import { useState } from "react";

interface OnboardingChatProps {
  agentMessage: string;
  onRespond: (response: string) => void;
  loading: boolean;
}

export function OnboardingChat({
  agentMessage,
  onRespond,
  loading,
}: OnboardingChatProps) {
  const [input, setInput] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;
    onRespond(input.trim());
    setInput("");
  };

  return (
    <div className="space-y-4">
      {/* Agent message */}
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
        <p className="text-sm text-slate-400 mb-1">GClaw</p>
        <p className="whitespace-pre-wrap text-slate-100">{agentMessage}</p>
      </div>

      {/* User input */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="flex-1 border border-slate-600 bg-slate-800 text-slate-100 rounded-lg px-4 py-2 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="Type your response..."
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          {loading ? "..." : "Send"}
        </button>
      </form>
    </div>
  );
}
