"use client";

/**
 * /admin/user — Shared user profile and timezone.
 *
 * Top card sets the IANA timezone that agents use in their "# Current
 * time" prompt section and as the default tz for new crons. Below,
 * the textarea edits ``user.md`` — the "# About the User" context
 * injected into every agent's system prompt.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";

// Curated fallback for browsers that don't implement
// Intl.supportedValuesOf("timeZone"). Covers the common cases;
// users can always type any IANA name into the datalist.
const FALLBACK_TIMEZONES: string[] = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Anchorage",
  "Pacific/Honolulu",
  "America/Toronto",
  "America/Sao_Paulo",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Europe/Madrid",
  "Europe/Rome",
  "Europe/Amsterdam",
  "Europe/Dublin",
  "Africa/Johannesburg",
  "Asia/Dubai",
  "Asia/Karachi",
  "Asia/Kolkata",
  "Asia/Shanghai",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Asia/Seoul",
  "Australia/Sydney",
  "Australia/Melbourne",
  "Pacific/Auckland",
];

function allTimezones(): string[] {
  try {
    const anyIntl = Intl as unknown as {
      supportedValuesOf?: (k: string) => string[];
    };
    if (typeof anyIntl.supportedValuesOf === "function") {
      const all = anyIntl.supportedValuesOf("timeZone");
      if (all && all.length > 0) return all;
    }
  } catch {
    /* fall through */
  }
  return FALLBACK_TIMEZONES;
}

function formatLocalClock(tz: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: tz,
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short",
    }).format(new Date());
  } catch {
    return `(invalid timezone: ${tz})`;
  }
}

function TimezoneCard() {
  const { getIdToken } = useAuth();
  const api = useMemo(() => createApiClient(getIdToken), [getIdToken]);

  const [current, setCurrent] = useState<string>("UTC");
  const [selected, setSelected] = useState<string>("UTC");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [clock, setClock] = useState<string>("");

  const zones = useMemo(() => allTimezones(), []);
  const browserTz = useMemo(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .getSystemTimezone()
      .then((res) => {
        if (cancelled) return;
        setCurrent(res.timezone);
        setSelected(res.timezone);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Failed to load timezone");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  useEffect(() => {
    setClock(formatLocalClock(selected));
    const id = setInterval(() => setClock(formatLocalClock(selected)), 30_000);
    return () => clearInterval(id);
  }, [selected]);

  const dirty = selected !== current;

  async function save() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const res = await api.updateSystemTimezone(selected);
      setCurrent(res.timezone);
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-3 rounded-md border border-slate-700 bg-slate-900/60 p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
          Timezone
        </h2>
        <span className="font-mono text-[11px] text-paper-40">
          {loading ? "…" : clock}
        </span>
      </div>
      <p className="text-[12px] text-paper-60">
        Injected into every agent&apos;s <span className="font-mono">#&nbsp;Current&nbsp;time</span> prompt
        and used as the default timezone for new crons. Pick an IANA
        name or type one.
      </p>
      {error && (
        <div className="rounded-md border border-red-700 bg-red-900/20 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <input
          list="tz-options"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          disabled={loading || saving}
          className="min-w-[240px] flex-1 rounded-md border border-slate-600 bg-slate-950 px-3 py-1.5 font-mono text-sm text-slate-200 focus:border-indigo-500 focus:outline-none"
          placeholder="e.g. America/Chicago"
          spellCheck={false}
        />
        <datalist id="tz-options">
          {zones.map((tz) => (
            <option key={tz} value={tz} />
          ))}
        </datalist>
        {browserTz && browserTz !== selected && (
          <button
            type="button"
            onClick={() => setSelected(browserTz)}
            className="rounded-md border border-slate-600 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
            title={`Set to your browser's detected timezone: ${browserTz}`}
          >
            Use {browserTz}
          </button>
        )}
        <button
          type="button"
          onClick={save}
          disabled={!dirty || saving}
          className="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
      <p className="text-[11px] text-paper-40">
        Active: <span className="font-mono text-slate-300">{current}</span>
        {dirty && <span className="ml-2 text-amber-400">• unsaved change</span>}
        {saved && <span className="ml-2 text-green-400">• saved</span>}
      </p>
    </div>
  );
}

function UserProfileEditor() {
  const { getIdToken } = useAuth();
  const api = useMemo(() => createApiClient(getIdToken), [getIdToken]);

  const [content, setContent] = useState("");
  const [baseline, setBaseline] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getUserProfile();
      setContent(res.content);
      setBaseline(res.content);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load profile");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  const dirty = content !== baseline;

  async function save() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await api.updateUserProfile(content);
      setBaseline(content);
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-400 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      {error && (
        <div className="rounded-md border border-red-700 bg-red-900/20 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        spellCheck={false}
        className="min-h-[480px] w-full rounded-md border border-slate-700 bg-slate-950 p-4 font-mono text-[13px] leading-relaxed text-slate-200 focus:border-indigo-500 focus:outline-none"
        placeholder="# About the User&#10;&#10;Stable facts about who the user is…"
      />
      <div className="flex items-center justify-between">
        <p className="text-[11px] text-paper-40">
          {content.length.toLocaleString()} chars
          {dirty && <span className="ml-2 text-amber-400">• unsaved</span>}
          {saved && <span className="ml-2 text-green-400">• saved</span>}
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setContent(baseline)}
            disabled={!dirty || saving}
            className="rounded-md border border-slate-600 px-4 py-1.5 text-sm text-slate-300 hover:bg-slate-800 disabled:opacity-40"
          >
            Reset
          </button>
          <button
            type="button"
            onClick={save}
            disabled={!dirty || saving}
            className="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

function UserProfileContent() {
  return (
    <div className="flex h-full flex-col bg-ink-900 text-paper">
      <header className="hairline-b px-8 pt-6 pb-5">
        <div className="label-caps mb-1.5">§ 12 · USER</div>
        <h1 className="font-display text-[30px] italic leading-none">
          About the User
        </h1>
        <p className="mt-2 max-w-2xl font-body text-[13px] text-paper-60">
          Shared context injected as <span className="font-mono">#&nbsp;About&nbsp;the&nbsp;User</span>{" "}
          into every agent&apos;s system prompt. Keep it to stable facts —
          name, role, timezone, communication preferences. Evolving
          preferences live in Memory Bank and are injected separately.
        </p>
      </header>

      <main className="flex-1 overflow-y-auto p-6 space-y-6">
        <TimezoneCard />
        <UserProfileEditor />
      </main>
    </div>
  );
}

export default function UserProfilePage() {
  return (
    <AppShell>
      <UserProfileContent />
    </AppShell>
  );
}
