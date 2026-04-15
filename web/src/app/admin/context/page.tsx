"use client";

/**
 * Admin page: Shared Context.
 *
 * Browse and manage the Firestore+GCS shared-context system that agents
 * use to exchange data. Namespaces on the left, entries on the right.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AppShell } from "@/components/layout/app-shell";
import { createApiClient, type ApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";
import type {
  ContextEntry,
  ContextNamespaceSummary,
} from "@/types";
import {
  ConfirmDialog,
  ErrorBanner,
  INPUT_CLS,
  LABEL_CLS,
  Modal,
} from "@/components/admin/models/shared";

// ---------- helpers ----------

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const diffMs = d.getTime() - Date.now();
  const past = diffMs < 0;
  const abs = Math.abs(diffMs);
  const sec = Math.round(abs / 1000);
  const min = Math.round(sec / 60);
  const hr = Math.round(min / 60);
  const day = Math.round(hr / 24);
  let core: string;
  if (sec < 45) core = `${sec}s`;
  else if (min < 60) core = `${min}m`;
  else if (hr < 24) core = `${hr}h`;
  else if (day < 365) core = `${day}d`;
  else core = `${Math.round(day / 365)}y`;
  return past ? `${core} ago` : `in ${core}`;
}

function looksLikeMarkdown(entry: ContextEntry): boolean {
  if (!entry.blob_mime) return true;
  return entry.blob_mime === "text/markdown" || entry.blob_mime === "text/x-markdown";
}

function MetadataChips({
  metadata,
}: {
  metadata: Record<string, unknown>;
}) {
  const keys = Object.keys(metadata || {});
  if (keys.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {keys.map((k) => {
        const raw = metadata[k];
        const value =
          typeof raw === "string" || typeof raw === "number" || typeof raw === "boolean"
            ? String(raw)
            : JSON.stringify(raw);
        return (
          <span
            key={k}
            className="rounded border border-slate-600 bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300"
            title={`${k}: ${value}`}
          >
            <span className="text-slate-500">{k}</span>
            <span className="mx-1 text-slate-600">=</span>
            <span className="font-mono">{value.length > 40 ? value.slice(0, 37) + "…" : value}</span>
          </span>
        );
      })}
    </div>
  );
}

// ---------- image blob (lazy) ----------

function BlobImage({ api, id, mime }: { api: ApiClient; id: string; mime: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    api
      .getContextBlobUrl(id)
      .then((res) => {
        if (!cancelled) setUrl(res.url);
      })
      .catch((e) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : "Failed to fetch signed URL");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api, id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center rounded border border-slate-700 bg-slate-950 py-10">
        <div className="h-6 w-6 animate-spin rounded-full border-4 border-indigo-400 border-t-transparent" />
      </div>
    );
  }
  if (err || !url) {
    return (
      <div className="rounded border border-red-700 bg-red-900/20 px-3 py-2 text-xs text-red-300">
        Failed to fetch image: {err ?? "unknown error"}
      </div>
    );
  }
  return (
    <div className="overflow-hidden rounded border border-slate-700 bg-slate-950">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={url}
        alt={`context ${id} (${mime})`}
        loading="lazy"
        className="max-h-96 w-auto max-w-full"
      />
    </div>
  );
}

// ---------- text blob (on-demand) ----------

function BlobTextLink({ api, id, mime }: { api: ApiClient; id: string; mime: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function fetchUrl() {
    setLoading(true);
    setErr(null);
    try {
      const res = await api.getContextBlobUrl(id);
      setUrl(res.url);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to fetch signed URL");
    } finally {
      setLoading(false);
    }
  }

  if (url) {
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-xs">
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-slate-200 hover:bg-slate-700"
          >
            Open in new tab
          </a>
          <span className="text-slate-500">({mime})</span>
        </div>
        <iframe
          src={url}
          title={`context ${id}`}
          className="h-64 w-full rounded border border-slate-700 bg-slate-950"
        />
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={fetchUrl}
        disabled={loading}
        className="rounded-md border border-slate-600 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-700 disabled:opacity-50"
      >
        {loading ? "Fetching…" : `Fetch blob (${mime})`}
      </button>
      {err && <span className="text-xs text-red-400">{err}</span>}
    </div>
  );
}

// ---------- binary blob ----------

function BlobBinary({ api, id, mime }: { api: ApiClient; id: string; mime: string }) {
  const [copied, setCopied] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function copyUrl() {
    setErr(null);
    try {
      const res = await api.getContextBlobUrl(id);
      await navigator.clipboard.writeText(res.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to copy signed URL");
    }
  }

  return (
    <div className="rounded border border-slate-700 bg-slate-950 px-3 py-3 text-xs text-slate-400">
      <div className="flex items-center justify-between gap-3">
        <span>
          Binary blob —{" "}
          <span className="font-mono text-slate-300">{mime || "unknown"}</span>
        </span>
        <button
          type="button"
          onClick={copyUrl}
          className="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-slate-200 hover:bg-slate-700"
        >
          {copied ? "Copied!" : "Copy signed URL"}
        </button>
      </div>
      {err && <div className="mt-2 text-red-400">{err}</div>}
    </div>
  );
}

// ---------- entry card ----------

function EntryBody({ api, entry }: { api: ApiClient; entry: ContextEntry }) {
  const hasContent = entry.content !== null && entry.content !== undefined;
  const mime = entry.blob_mime || "";

  if (hasContent) {
    if (looksLikeMarkdown(entry)) {
      return (
        <div className="prose prose-invert prose-sm max-w-none text-slate-200">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {entry.content ?? ""}
          </ReactMarkdown>
        </div>
      );
    }
    return (
      <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded border border-slate-700 bg-slate-950 p-3 text-xs text-slate-200">
        {entry.content}
      </pre>
    );
  }

  if (entry.blob_url) {
    if (mime.startsWith("image/")) {
      return <BlobImage api={api} id={entry.id} mime={mime} />;
    }
    if (mime.startsWith("text/") || mime === "application/json") {
      return <BlobTextLink api={api} id={entry.id} mime={mime} />;
    }
    return <BlobBinary api={api} id={entry.id} mime={mime} />;
  }

  return (
    <div className="text-xs italic text-slate-500">
      (empty entry — no content and no blob)
    </div>
  );
}

function EntryCard({
  api,
  entry,
  onDelete,
}: {
  api: ApiClient;
  entry: ContextEntry;
  onDelete: (entry: ContextEntry) => void;
}) {
  const [copied, setCopied] = useState(false);

  async function copyId() {
    try {
      await navigator.clipboard.writeText(entry.id);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/60 px-4 py-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
            <span className="font-medium text-slate-200">
              {entry.created_by || "unknown"}
            </span>
            <span className="text-slate-600">·</span>
            <span title={entry.timestamp}>{formatRelative(entry.timestamp)}</span>
            <span className="text-slate-600">·</span>
            <span
              className="rounded border border-amber-800/50 bg-amber-900/20 px-1.5 py-0.5 text-[10px] text-amber-300"
              title={`expires ${entry.expires_at}`}
            >
              expires {formatRelative(entry.expires_at)}
            </span>
          </div>
          <div className="mt-0.5 font-mono text-[11px] text-slate-500">{entry.id}</div>
        </div>
        <div className="flex items-center gap-1 text-xs">
          <button
            type="button"
            onClick={copyId}
            className="rounded px-1.5 py-0.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
          >
            {copied ? "Copied!" : "Copy ID"}
          </button>
          <button
            type="button"
            onClick={() => onDelete(entry)}
            className="rounded px-1.5 py-0.5 text-slate-400 hover:bg-red-900/40 hover:text-red-300"
          >
            Delete
          </button>
        </div>
      </div>

      <div className="mt-3">
        <EntryBody api={api} entry={entry} />
      </div>

      <MetadataChips metadata={entry.metadata || {}} />
    </div>
  );
}

// ---------- new entry modal ----------

function NewEntryForm({
  namespaces,
  initialNamespace,
  onSubmit,
  onCancel,
}: {
  namespaces: ContextNamespaceSummary[];
  initialNamespace: string | null;
  onSubmit: (body: {
    namespace: string;
    content: string;
    metadata?: Record<string, unknown>;
  }) => Promise<void>;
  onCancel: () => void;
}) {
  const [namespace, setNamespace] = useState(initialNamespace ?? "");
  const [content, setContent] = useState("");
  const [metadataRaw, setMetadataRaw] = useState("");
  const [metadataErr, setMetadataErr] = useState<string | null>(null);
  const [submitErr, setSubmitErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitErr(null);
    setMetadataErr(null);

    if (!namespace.trim()) {
      setSubmitErr("Namespace is required.");
      return;
    }
    if (!content.trim()) {
      setSubmitErr("Content is required.");
      return;
    }

    let metadata: Record<string, unknown> | undefined;
    if (metadataRaw.trim()) {
      try {
        const parsed = JSON.parse(metadataRaw);
        if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
          setMetadataErr("Metadata must be a JSON object.");
          return;
        }
        metadata = parsed as Record<string, unknown>;
      } catch (err) {
        setMetadataErr(
          `Invalid JSON: ${err instanceof Error ? err.message : "parse error"}`,
        );
        return;
      }
    }

    setBusy(true);
    try {
      await onSubmit({
        namespace: namespace.trim(),
        content,
        metadata,
      });
    } catch (err) {
      setSubmitErr(err instanceof Error ? err.message : "Failed to create entry");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className={LABEL_CLS} htmlFor="ctx-namespace">
          Namespace
        </label>
        <input
          id="ctx-namespace"
          list="ctx-namespace-options"
          type="text"
          value={namespace}
          onChange={(e) => setNamespace(e.target.value)}
          className={INPUT_CLS}
          placeholder="e.g. research/web-findings"
          required
        />
        <datalist id="ctx-namespace-options">
          {namespaces.map((n) => (
            <option key={n.namespace} value={n.namespace} />
          ))}
        </datalist>
      </div>

      <div>
        <label className={LABEL_CLS} htmlFor="ctx-content">
          Content
        </label>
        <textarea
          id="ctx-content"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          className={`${INPUT_CLS} min-h-[160px] font-mono text-xs`}
          placeholder="Markdown or plain text…"
          required
        />
      </div>

      <div>
        <label className={LABEL_CLS} htmlFor="ctx-metadata">
          Metadata (optional JSON object)
        </label>
        <textarea
          id="ctx-metadata"
          value={metadataRaw}
          onChange={(e) => setMetadataRaw(e.target.value)}
          className={`${INPUT_CLS} min-h-[80px] font-mono text-xs`}
          placeholder='{"source": "manual"}'
        />
        {metadataErr && (
          <p className="mt-1 text-xs text-red-400">{metadataErr}</p>
        )}
      </div>

      <ErrorBanner error={submitErr} />

      <div className="flex justify-end gap-3">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-slate-600 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {busy ? "Creating…" : "Create entry"}
        </button>
      </div>
    </form>
  );
}

// ---------- main ----------

function ContextContent() {
  const { getIdToken } = useAuth();
  const api = useMemo(() => createApiClient(getIdToken), [getIdToken]);

  const [namespaces, setNamespaces] = useState<ContextNamespaceSummary[]>([]);
  const [selectedNs, setSelectedNs] = useState<string | null>(null);
  const [entries, setEntries] = useState<ContextEntry[]>([]);

  const [loadingNs, setLoadingNs] = useState(true);
  const [loadingEntries, setLoadingEntries] = useState(false);
  const [nsError, setNsError] = useState<string | null>(null);
  const [entriesError, setEntriesError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [showNewForm, setShowNewForm] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ContextEntry | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const loadNamespaces = useCallback(async () => {
    try {
      const list = await api.listContextNamespaces();
      setNamespaces(list);
      setNsError(null);
      setSelectedNs((prev) => {
        if (prev && list.some((n) => n.namespace === prev)) return prev;
        return list[0]?.namespace ?? null;
      });
    } catch (err) {
      setNsError(err instanceof Error ? err.message : "Failed to load namespaces");
    } finally {
      setLoadingNs(false);
    }
  }, [api]);

  const loadEntries = useCallback(async () => {
    if (!selectedNs) {
      setEntries([]);
      return;
    }
    setLoadingEntries(true);
    try {
      const list = await api.listContextEntries(selectedNs, { limit: 20 });
      setEntries(list);
      setEntriesError(null);
    } catch (err) {
      setEntriesError(
        err instanceof Error ? err.message : "Failed to load entries",
      );
    } finally {
      setLoadingEntries(false);
    }
  }, [api, selectedNs]);

  useEffect(() => {
    loadNamespaces();
  }, [loadNamespaces]);

  useEffect(() => {
    loadEntries();
  }, [loadEntries]);

  async function handleCreate(body: {
    namespace: string;
    content: string;
    metadata?: Record<string, unknown>;
  }) {
    const created = await api.createContextEntry(body);
    setShowNewForm(false);
    setSelectedNs(created.namespace);
    await loadNamespaces();
    await loadEntries();
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    try {
      await api.deleteContextEntry(deleteTarget.id);
      setDeleteTarget(null);
      await loadNamespaces();
      await loadEntries();
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to delete entry",
      );
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <div className="flex h-screen flex-col bg-slate-900 text-slate-100">
      <header className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
        <div>
          <h1 className="text-2xl font-bold">Shared Context</h1>
          <p className="mt-0.5 text-sm text-slate-400">
            Browse and manage the Firestore + GCS shared-context store used for
            agent-to-agent data exchange.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowNewForm(true)}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
        >
          + New entry
        </button>
      </header>

      <main className="flex-1 overflow-y-auto p-6">
        {actionError && (
          <div className="mb-4">
            <ErrorBanner error={actionError} />
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
          {/* Namespace column */}
          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
              Namespaces
            </h2>
            <ErrorBanner error={nsError} />

            {loadingNs ? (
              <div className="flex items-center justify-center py-16">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-400 border-t-transparent" />
              </div>
            ) : namespaces.length === 0 ? (
              <div className="rounded-md border border-slate-700 bg-slate-900 px-4 py-8 text-center text-sm text-slate-500">
                No namespaces yet — click &quot;+ New entry&quot; to create the
                first one.
              </div>
            ) : (
              <div className="space-y-2">
                {namespaces.map((n) => {
                  const active = n.namespace === selectedNs;
                  return (
                    <button
                      key={n.namespace}
                      type="button"
                      onClick={() => setSelectedNs(n.namespace)}
                      className={`w-full rounded-lg border px-4 py-3 text-left transition-colors ${
                        active
                          ? "border-indigo-500 bg-indigo-600/10"
                          : "border-slate-700 bg-slate-900/60 hover:bg-slate-800/60"
                      }`}
                    >
                      <div className="truncate font-medium text-slate-100">
                        {n.namespace}
                      </div>
                      <div className="mt-1 flex items-center justify-between text-xs text-slate-400">
                        <span>
                          {n.count} {n.count === 1 ? "entry" : "entries"}
                        </span>
                        <span title={n.latest_at ?? ""}>
                          {formatRelative(n.latest_at)}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          {/* Entries column */}
          <section className="space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
              {selectedNs ? `Entries in ${selectedNs}` : "Entries"}
            </h2>
            <ErrorBanner error={entriesError} />

            {!selectedNs ? (
              <div className="rounded-md border border-slate-700 bg-slate-900 px-4 py-8 text-center text-sm text-slate-500">
                Select a namespace to view its entries.
              </div>
            ) : loadingEntries ? (
              <div className="flex items-center justify-center py-10">
                <div className="h-6 w-6 animate-spin rounded-full border-4 border-indigo-400 border-t-transparent" />
              </div>
            ) : entries.length === 0 ? (
              <div className="rounded-md border border-slate-700 bg-slate-900 px-4 py-8 text-center text-sm text-slate-500">
                This namespace has no entries.
              </div>
            ) : (
              <div className="space-y-3">
                {entries.map((e) => (
                  <EntryCard
                    key={e.id}
                    api={api}
                    entry={e}
                    onDelete={setDeleteTarget}
                  />
                ))}
              </div>
            )}
          </section>
        </div>
      </main>

      {showNewForm && (
        <Modal
          title="New context entry"
          onClose={() => setShowNewForm(false)}
          wide
        >
          <NewEntryForm
            namespaces={namespaces}
            initialNamespace={selectedNs}
            onSubmit={handleCreate}
            onCancel={() => setShowNewForm(false)}
          />
        </Modal>
      )}

      {deleteTarget && (
        <ConfirmDialog
          title="Delete context entry?"
          message={
            <>
              Delete entry{" "}
              <span className="font-mono text-xs">{deleteTarget.id}</span> in
              namespace <strong>{deleteTarget.namespace}</strong>? This cannot
              be undone.
            </>
          }
          confirmLabel="Delete entry"
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
          busy={deleteBusy}
        />
      )}
    </div>
  );
}

export default function ContextAdminPage() {
  return (
    <AppShell>
      <ContextContent />
    </AppShell>
  );
}
