"use client";

/**
 * NewCronModal — wraps CreateCronForm in a slide-over drawer for "create" mode.
 * Mirrors the look of CronEditDrawer.
 */

import { useEffect } from "react";
import type { CronInfo } from "@/types";
import { CreateCronForm } from "@/components/crons/create-cron-form";

interface NewCronModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (cron: CronInfo) => void;
}

export function NewCronModal({ open, onClose, onCreated }: NewCronModalProps) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex"
      role="dialog"
      aria-modal="true"
      aria-label="New cron"
    >
      <div
        className="flex-1 bg-black/50"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside className="flex h-full w-full max-w-2xl flex-col border-l border-slate-700 bg-slate-900 shadow-2xl">
        <header className="flex items-center justify-between border-b border-slate-700 px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-slate-100">New Cron</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Schedule a recurring or one-off task
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-md p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
          >
            <svg
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-5">
          <CreateCronForm
            onCreated={(c) => {
              onCreated(c);
              onClose();
            }}
            onSaved={(c) => {
              onCreated(c);
              onClose();
            }}
            onCancel={onClose}
          />
        </div>
      </aside>
    </div>
  );
}
