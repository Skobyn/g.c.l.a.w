"use client";

import { useState } from "react";

interface ChipInputProps {
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
}

/**
 * Simple tag-style input. Enter/comma adds a chip, backspace on empty removes last.
 */
export function ChipInput({
  values,
  onChange,
  placeholder,
  disabled,
}: ChipInputProps) {
  const [draft, setDraft] = useState("");

  function commit(raw: string) {
    const v = raw.trim();
    if (!v) return;
    if (values.includes(v)) {
      setDraft("");
      return;
    }
    onChange([...values, v]);
    setDraft("");
  }

  function remove(idx: number) {
    const next = values.slice();
    next.splice(idx, 1);
    onChange(next);
  }

  return (
    <div
      className={`flex flex-wrap items-center gap-1.5 rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5 ${
        disabled ? "opacity-50" : "focus-within:border-indigo-500"
      }`}
    >
      {values.map((v, i) => (
        <span
          key={`${v}-${i}`}
          className="inline-flex items-center gap-1 rounded-md border border-slate-600 bg-slate-800 px-2 py-0.5 text-xs text-slate-200"
        >
          {v}
          {!disabled && (
            <button
              type="button"
              onClick={() => remove(i)}
              className="text-slate-400 hover:text-red-300"
              aria-label={`Remove ${v}`}
            >
              ×
            </button>
          )}
        </span>
      ))}
      <input
        type="text"
        value={draft}
        disabled={disabled}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            commit(draft);
          } else if (e.key === "Backspace" && draft === "" && values.length > 0) {
            e.preventDefault();
            remove(values.length - 1);
          }
        }}
        onBlur={() => commit(draft)}
        placeholder={placeholder ?? "Type and press Enter"}
        className="min-w-[120px] flex-1 bg-transparent px-1 py-0.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none"
      />
    </div>
  );
}
