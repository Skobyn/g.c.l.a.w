"use client";

/**
 * Inline "Test" button + result badge for a catalog model.
 */

import { useState } from "react";
import type { TestModelResult } from "@/types";

interface TestConnectionBadgeProps {
  modelId: string;
  onTest: (id: string) => Promise<TestModelResult>;
}

export function TestConnectionBadge({
  modelId,
  onTest,
}: TestConnectionBadgeProps) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<TestModelResult | null>(null);

  async function run() {
    setBusy(true);
    try {
      const r = await onTest(modelId);
      setResult(r);
    } catch (err) {
      setResult({
        ok: false,
        latency_ms: 0,
        error: err instanceof Error ? err.message : "Test failed",
        sample_response: null,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={run}
        disabled={busy}
        className="rounded-md border border-slate-600 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
      >
        {busy ? "Testing..." : "Test"}
      </button>
      {result && !busy && (
        result.ok ? (
          <span
            className="rounded-md border border-green-700 bg-green-600/20 px-2 py-0.5 text-[10px] font-bold text-green-300"
            title={result.sample_response ?? undefined}
          >
            OK · {result.latency_ms}ms
          </span>
        ) : (
          <span
            className="rounded-md border border-red-700 bg-red-900/40 px-2 py-0.5 text-[10px] font-bold text-red-300"
            title={result.error ?? "Unknown error"}
          >
            FAIL
          </span>
        )
      )}
    </div>
  );
}
