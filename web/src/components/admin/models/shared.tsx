"use client";

/**
 * Shared UI bits for the model-catalog admin surface.
 * Kept local to /admin/models; matches slate-900 / indigo accents.
 */

import type { ProviderKind } from "@/types";

export const INPUT_CLS =
  "w-full rounded-md border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500";
export const LABEL_CLS = "block text-xs font-medium text-slate-400 mb-1";

export const PROVIDER_KIND_LABELS: Record<ProviderKind, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  google_gemini: "Google Gemini API",
  google_vertex: "Google Vertex AI",
  openrouter: "OpenRouter",
  ollama: "Ollama (local)",
  groq: "Groq",
  together: "Together AI",
  custom_openai: "Custom OpenAI-compatible",
  anthropic_oauth: "Anthropic (Claude Code OAuth)",
};

const KIND_BADGE_CLS: Record<ProviderKind, string> = {
  openai: "border-green-700 bg-green-600/20 text-green-300",
  anthropic: "border-orange-700 bg-orange-600/20 text-orange-300",
  google_gemini: "border-blue-700 bg-blue-600/20 text-blue-300",
  google_vertex: "border-sky-700 bg-sky-600/20 text-sky-300",
  openrouter: "border-purple-700 bg-purple-600/20 text-purple-300",
  ollama: "border-slate-600 bg-slate-700/40 text-slate-200",
  groq: "border-pink-700 bg-pink-600/20 text-pink-300",
  together: "border-amber-700 bg-amber-600/20 text-amber-300",
  custom_openai: "border-teal-700 bg-teal-600/20 text-teal-300",
  anthropic_oauth: "border-zinc-600 bg-zinc-700/30 text-amber-200",
};

export function KindBadge({ kind }: { kind: ProviderKind }) {
  return (
    <span
      className={`rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${KIND_BADGE_CLS[kind]}`}
    >
      {PROVIDER_KIND_LABELS[kind]}
    </span>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <label
      className={`flex items-center gap-2 text-sm text-slate-300 ${
        disabled ? "opacity-50" : "cursor-pointer"
      }`}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 rounded border-slate-600 bg-slate-900 text-indigo-500 focus:ring-indigo-500"
      />
      <span>{label}</span>
    </label>
  );
}

export function Modal({
  title,
  onClose,
  children,
  wide,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        className={`flex max-h-[90vh] w-full flex-col rounded-lg border border-slate-700 bg-slate-900 shadow-xl ${
          wide ? "max-w-3xl" : "max-w-xl"
        }`}
      >
        <div className="flex items-center justify-between border-b border-slate-700 px-5 py-3">
          <h2 className="text-base font-semibold text-slate-100">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-md p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
          >
            <svg
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>
  );
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel = "Delete",
  onConfirm,
  onCancel,
  busy,
}: {
  title: string;
  message: React.ReactNode;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
}) {
  return (
    <Modal title={title} onClose={onCancel}>
      <div className="space-y-4">
        <div className="text-sm text-slate-300">{message}</div>
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-slate-600 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
          >
            {busy ? "Working..." : confirmLabel}
          </button>
        </div>
      </div>
    </Modal>
  );
}

export function ErrorBanner({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div className="rounded-md border border-red-700 bg-red-900/30 px-4 py-3 text-sm text-red-400">
      {error}
    </div>
  );
}
