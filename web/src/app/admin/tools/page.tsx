"use client";

/**
 * /admin/tools — Tool Catalog CRUD.
 *
 * Sibling of /admin/models. Lists every tool, lets the user add /
 * edit / delete / test in place. Kind-specific config lives behind
 * ToolKindForm; on kind change we reset the config dict so the
 * previous kind's stale fields never reach the server.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { createApiClient } from "@/lib/api-client";
import { useAuth } from "@/contexts/auth-context";
import type { TestToolResult, ToolKind, ToolRecord } from "@/types";
import { ToolKindForm } from "@/components/admin/tools/ToolKindForm";

const KIND_LABELS: Record<ToolKind, string> = {
  builtin: "Builtin",
  mcp: "MCP Server",
  http_api: "HTTP/OpenAPI",
  code_exec: "Code Exec",
};

const KIND_DEFAULT_CONFIG: Record<ToolKind, Record<string, unknown>> = {
  builtin: { kind: "builtin", function_path: "" },
  mcp: { kind: "mcp", transport: "stdio", endpoint: "", env: {}, allowed_tools: null },
  http_api: {
    kind: "http_api",
    spec_url: "",
    base_url: "",
    auth: { kind: "none" },
    allowed_operations: null,
  },
  code_exec: {
    kind: "code_exec",
    runtime: "python3.12",
    timeout_seconds: 30,
    memory_mb: 256,
    network: "none",
    allowed_modules: [],
  },
};

function ToolsContent() {
  const { getIdToken } = useAuth();
  const api = useMemo(() => createApiClient(getIdToken), [getIdToken]);

  const [tools, setTools] = useState<ToolRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editing, setEditing] = useState<ToolRecord | null>(null);
  const [newOpen, setNewOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await api.listTools();
      setTools(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load tools");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex h-full flex-col bg-ink-900 text-paper">
      <header className="hairline-b flex items-end justify-between px-8 pt-6 pb-5">
        <div>
          <div className="label-caps mb-1.5">§ TOOLS</div>
          <h1 className="font-display text-[30px] italic leading-none">Tool Catalog</h1>
          <p className="mt-2 max-w-2xl font-body text-[13px] text-paper-60">
            Register builtin functions, MCP servers, OpenAPI-backed APIs, and
            sandboxed code runners. Agents bind to entries via the catalog
            picker on <span className="font-mono">/admin/agents/[name]</span>.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setNewOpen(true)}
          className="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500"
        >
          + New tool
        </button>
      </header>

      <main className="flex-1 overflow-y-auto p-6">
        {error && (
          <div className="mb-4 rounded-md border border-red-700 bg-red-900/20 px-3 py-2 text-sm text-red-300">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-400 border-t-transparent" />
          </div>
        ) : tools.length === 0 ? (
          <div className="rounded-md border border-slate-700 bg-slate-900 px-4 py-10 text-center text-sm text-slate-500">
            No tools yet. Click &quot;+ New tool&quot; to add one.
          </div>
        ) : (
          <ToolTable
            tools={tools}
            onEdit={setEditing}
            onTest={async (t) => {
              try {
                const res = await api.testTool(t.id);
                return res;
              } catch (e) {
                return {
                  ok: false,
                  latency_ms: 0,
                  error: e instanceof Error ? e.message : "Test failed",
                  sample_response: null,
                };
              }
            }}
            onDelete={async (t) => {
              if (!confirm(`Delete tool "${t.name}"?`)) return;
              await api.deleteTool(t.id);
              await load();
            }}
          />
        )}
      </main>

      {newOpen && (
        <ToolEditor
          mode="create"
          initial={null}
          onClose={() => setNewOpen(false)}
          onSave={async (payload) => {
            await api.createTool(payload);
            setNewOpen(false);
            await load();
          }}
        />
      )}
      {editing && (
        <ToolEditor
          mode="edit"
          initial={editing}
          onClose={() => setEditing(null)}
          onSave={async (payload) => {
            await api.updateTool(editing.id, payload);
            setEditing(null);
            await load();
          }}
        />
      )}
    </div>
  );
}

interface ToolTableProps {
  tools: ToolRecord[];
  onEdit: (t: ToolRecord) => void;
  onDelete: (t: ToolRecord) => void | Promise<void>;
  onTest: (t: ToolRecord) => Promise<TestToolResult>;
}

function ToolTable({ tools, onEdit, onDelete, onTest }: ToolTableProps) {
  const [testResults, setTestResults] = useState<Record<string, TestToolResult | null>>({});
  const [testing, setTesting] = useState<Record<string, boolean>>({});
  return (
    <div className="overflow-x-auto rounded-md border border-slate-700">
      <table className="w-full text-sm">
        <thead className="bg-slate-900 text-left text-[11px] uppercase tracking-wide text-slate-400">
          <tr>
            <th className="px-3 py-2">Name</th>
            <th className="px-3 py-2">Kind</th>
            <th className="px-3 py-2">Enabled</th>
            <th className="px-3 py-2">Test</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {tools.map((t) => {
            const res = testResults[t.id];
            return (
              <tr key={t.id} className="border-t border-slate-800">
                <td className="px-3 py-2 font-mono text-[13px] text-slate-100">{t.name}</td>
                <td className="px-3 py-2 text-[12px] text-slate-300">{KIND_LABELS[t.kind]}</td>
                <td className="px-3 py-2">
                  <span
                    className={`inline-block rounded px-1.5 py-0.5 text-[10px] ${
                      t.enabled
                        ? "border border-green-700 bg-green-900/30 text-green-300"
                        : "border border-slate-600 bg-slate-800 text-slate-400"
                    }`}
                  >
                    {t.enabled ? "on" : "off"}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <button
                    type="button"
                    className="rounded border border-slate-600 px-2 py-0.5 text-xs text-slate-200 hover:bg-slate-800 disabled:opacity-40"
                    disabled={!!testing[t.id]}
                    onClick={async () => {
                      setTesting((s) => ({ ...s, [t.id]: true }));
                      const result = await onTest(t);
                      setTesting((s) => ({ ...s, [t.id]: false }));
                      setTestResults((s) => ({ ...s, [t.id]: result }));
                    }}
                  >
                    {testing[t.id] ? "…" : "Test"}
                  </button>
                  {res && (
                    <span
                      className={`ml-2 text-[11px] ${
                        res.ok ? "text-green-400" : "text-red-400"
                      }`}
                      title={res.error || undefined}
                    >
                      {res.ok ? `✓ ${res.latency_ms}ms` : `✗ ${res.error?.slice(0, 40)}`}
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-right text-[12px]">
                  <button
                    type="button"
                    onClick={() => onEdit(t)}
                    className="rounded px-1.5 py-0.5 text-slate-300 hover:bg-slate-800"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(t)}
                    className="ml-1 rounded px-1.5 py-0.5 text-slate-400 hover:bg-red-900/40 hover:text-red-300"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

interface ToolEditorProps {
  mode: "create" | "edit";
  initial: ToolRecord | null;
  onClose: () => void;
  onSave: (payload: {
    name: string;
    config: Record<string, unknown>;
    enabled: boolean;
    credential_ref: string | null;
  }) => Promise<void>;
}

function ToolEditor({ mode, initial, onClose, onSave }: ToolEditorProps) {
  const [name, setName] = useState(initial?.name ?? "");
  const [kind, setKind] = useState<ToolKind>(initial?.kind ?? "builtin");
  const [config, setConfig] = useState<Record<string, unknown>>(
    initial?.config ?? KIND_DEFAULT_CONFIG["builtin"],
  );
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);
  const [credRef, setCredRef] = useState(initial?.credential_ref ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-[620px] max-h-[90vh] overflow-y-auto rounded-lg border border-slate-700 bg-slate-900 p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-100">
            {mode === "create" ? "New tool" : `Edit ${initial?.name}`}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200"
          >
            ×
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">Name</label>
            <input
              className="w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="web_search"
              spellCheck={false}
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-300">Kind</label>
              <select
                className="w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-1.5 text-sm text-slate-100"
                value={kind}
                disabled={mode === "edit"}
                onChange={(e) => {
                  const k = e.target.value as ToolKind;
                  setKind(k);
                  setConfig({ ...KIND_DEFAULT_CONFIG[k] });
                }}
              >
                {(Object.keys(KIND_LABELS) as ToolKind[]).map((k) => (
                  <option key={k} value={k}>
                    {KIND_LABELS[k]}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(e) => setEnabled(e.target.checked)}
                />
                Enabled
              </label>
            </div>
          </div>

          <div className="rounded-md border border-slate-700 bg-slate-950/50 p-3">
            <ToolKindForm kind={kind} config={config} onConfigChange={setConfig} />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">
              Credential Secret Manager path (optional)
            </label>
            <input
              className="w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-1.5 font-mono text-sm text-slate-100"
              value={credRef}
              onChange={(e) => setCredRef(e.target.value)}
              placeholder="projects/p/secrets/NAME/versions/latest"
              spellCheck={false}
            />
          </div>

          {error && (
            <div className="rounded-md border border-red-700 bg-red-900/20 px-3 py-2 text-xs text-red-300">
              {error}
            </div>
          )}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-slate-600 px-4 py-1.5 text-sm text-slate-300 hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={async () => {
              if (!name.trim()) {
                setError("Name is required");
                return;
              }
              setSaving(true);
              setError(null);
              try {
                await onSave({
                  name: name.trim(),
                  config,
                  enabled,
                  credential_ref: credRef.trim() || null,
                });
              } catch (e) {
                setError(e instanceof Error ? e.message : "Save failed");
              } finally {
                setSaving(false);
              }
            }}
            className="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ToolsAdminPage() {
  return (
    <AppShell>
      <ToolsContent />
    </AppShell>
  );
}
