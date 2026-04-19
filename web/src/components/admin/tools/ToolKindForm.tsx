"use client";

/**
 * Kind-specific form panels for the Tool Catalog.
 *
 * Each panel binds a subset of `config` keys to fields. The parent
 * page holds one `config` dict and swaps panels based on `kind`; on
 * kind change we reset the dict so stale keys from the previous kind
 * don't leak into the create payload.
 */

import type { ToolKind } from "@/types";

type ConfigUpdater = (next: Record<string, unknown>) => void;

const INPUT_CLS =
  "w-full rounded-md border border-slate-600 bg-slate-950 px-3 py-1.5 text-sm text-slate-100 focus:border-indigo-500 focus:outline-none";
const LABEL_CLS = "mb-1 block text-xs font-medium text-slate-300";

interface Props {
  kind: ToolKind;
  config: Record<string, unknown>;
  onConfigChange: ConfigUpdater;
}

export function ToolKindForm({ kind, config, onConfigChange }: Props) {
  if (kind === "builtin") return <BuiltinForm config={config} onConfigChange={onConfigChange} />;
  if (kind === "mcp") return <McpForm config={config} onConfigChange={onConfigChange} />;
  if (kind === "http_api") return <HttpApiForm config={config} onConfigChange={onConfigChange} />;
  if (kind === "code_exec") return <CodeExecForm config={config} onConfigChange={onConfigChange} />;
  return null;
}

// ---- builtin ----

function BuiltinForm({ config, onConfigChange }: { config: Record<string, unknown>; onConfigChange: ConfigUpdater }) {
  const fp = (config.function_path as string) || "";
  return (
    <div>
      <label className={LABEL_CLS}>Function path (dotted import)</label>
      <input
        className={INPUT_CLS}
        value={fp}
        onChange={(e) => onConfigChange({ ...config, kind: "builtin", function_path: e.target.value })}
        placeholder="gclaw.tools.research_tools.web_search"
        spellCheck={false}
      />
      <p className="mt-1 text-[11px] text-slate-500">
        Points at a @tool_export-decorated function in the running app.
      </p>
    </div>
  );
}

// ---- mcp ----

function McpForm({ config, onConfigChange }: { config: Record<string, unknown>; onConfigChange: ConfigUpdater }) {
  const transport = (config.transport as string) || "stdio";
  const endpoint = (config.endpoint as string) || "";
  const allowedTools = (config.allowed_tools as string[] | null) ?? null;
  const env = (config.env as Record<string, string>) || {};

  const envRows = Object.entries(env);

  const updateEnv = (next: Record<string, string>) => {
    onConfigChange({ ...config, kind: "mcp", env: next });
  };

  return (
    <div className="space-y-3">
      <div>
        <label className={LABEL_CLS}>Transport</label>
        <select
          className={INPUT_CLS}
          value={transport}
          onChange={(e) => onConfigChange({ ...config, kind: "mcp", transport: e.target.value })}
        >
          <option value="stdio">stdio (subprocess)</option>
          <option value="sse">sse</option>
          <option value="http">streamable http</option>
        </select>
      </div>
      <div>
        <label className={LABEL_CLS}>
          {transport === "stdio" ? "Command + args" : "Server URL"}
        </label>
        <input
          className={INPUT_CLS}
          value={endpoint}
          onChange={(e) => onConfigChange({ ...config, kind: "mcp", endpoint: e.target.value })}
          placeholder={transport === "stdio" ? "npx -y @modelcontextprotocol/server-filesystem /tmp" : "https://mcp.example.com/sse"}
          spellCheck={false}
        />
      </div>
      <div>
        <label className={LABEL_CLS}>Allowed tools (comma-separated; empty = all)</label>
        <input
          className={INPUT_CLS}
          value={(allowedTools || []).join(", ")}
          onChange={(e) => {
            const list = e.target.value
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean);
            onConfigChange({
              ...config,
              kind: "mcp",
              allowed_tools: list.length === 0 ? null : list,
            });
          }}
          placeholder="read_file, list_directory"
        />
      </div>
      <div>
        <label className={LABEL_CLS}>Env vars (value ${"{CREDENTIAL}"} pulls from Secret Manager)</label>
        <div className="space-y-1">
          {envRows.map(([k, v], i) => (
            <div key={i} className="flex gap-2">
              <input
                className={`${INPUT_CLS} w-48`}
                value={k}
                onChange={(e) => {
                  const next = { ...env };
                  delete next[k];
                  next[e.target.value] = v;
                  updateEnv(next);
                }}
                placeholder="GITHUB_TOKEN"
              />
              <input
                className={`${INPUT_CLS} flex-1`}
                value={v}
                onChange={(e) => updateEnv({ ...env, [k]: e.target.value })}
                placeholder="${CREDENTIAL}"
              />
              <button
                type="button"
                onClick={() => {
                  const next = { ...env };
                  delete next[k];
                  updateEnv(next);
                }}
                className="rounded border border-slate-600 px-2 text-xs text-slate-400 hover:bg-red-900/40 hover:text-red-300"
              >
                ×
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => updateEnv({ ...env, "": "" })}
            className="rounded border border-slate-600 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-800"
          >
            + env var
          </button>
        </div>
      </div>
    </div>
  );
}

// ---- http_api ----

function HttpApiForm({ config, onConfigChange }: { config: Record<string, unknown>; onConfigChange: ConfigUpdater }) {
  const specUrl = (config.spec_url as string) || "";
  const baseUrl = (config.base_url as string) || "";
  const auth = (config.auth as Record<string, unknown>) || { kind: "none" };
  const allowed = (config.allowed_operations as string[] | null) ?? null;

  return (
    <div className="space-y-3">
      <div>
        <label className={LABEL_CLS}>OpenAPI spec URL</label>
        <input
          className={INPUT_CLS}
          value={specUrl}
          onChange={(e) => onConfigChange({ ...config, kind: "http_api", spec_url: e.target.value || null })}
          placeholder="https://petstore.swagger.io/v2/swagger.json"
          spellCheck={false}
        />
        <p className="mt-1 text-[11px] text-slate-500">
          Or leave empty and paste a <span className="font-mono">spec_inline</span> JSON dict in the raw config (not yet in the UI).
        </p>
      </div>
      <div>
        <label className={LABEL_CLS}>Base URL</label>
        <input
          className={INPUT_CLS}
          value={baseUrl}
          onChange={(e) => onConfigChange({ ...config, kind: "http_api", base_url: e.target.value })}
          placeholder="https://petstore.example.com/v2"
          spellCheck={false}
        />
      </div>
      <div>
        <label className={LABEL_CLS}>Auth</label>
        <select
          className={INPUT_CLS}
          value={(auth.kind as string) || "none"}
          onChange={(e) => {
            const k = e.target.value;
            let next: Record<string, unknown> = { kind: k };
            if (k === "api_key") next = { ...next, location: "header", param_name: "X-API-Key", credential_ref: "" };
            if (["bearer", "basic", "oauth2"].includes(k)) next = { ...next, credential_ref: "" };
            onConfigChange({ ...config, kind: "http_api", auth: next });
          }}
        >
          <option value="none">none</option>
          <option value="api_key">api_key</option>
          <option value="bearer">bearer</option>
          <option value="basic">basic</option>
          <option value="oauth2">oauth2</option>
        </select>
      </div>
      {auth.kind === "api_key" && (
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className={LABEL_CLS}>Location</label>
            <select
              className={INPUT_CLS}
              value={(auth.location as string) || "header"}
              onChange={(e) => onConfigChange({ ...config, kind: "http_api", auth: { ...auth, location: e.target.value } })}
            >
              <option value="header">header</option>
              <option value="query">query</option>
            </select>
          </div>
          <div>
            <label className={LABEL_CLS}>Param name</label>
            <input
              className={INPUT_CLS}
              value={(auth.param_name as string) || ""}
              onChange={(e) => onConfigChange({ ...config, kind: "http_api", auth: { ...auth, param_name: e.target.value } })}
              placeholder="X-API-Key"
            />
          </div>
        </div>
      )}
      {(auth.kind === "api_key" ||
        auth.kind === "bearer" ||
        auth.kind === "basic" ||
        auth.kind === "oauth2") && (
        <div>
          <label className={LABEL_CLS}>Credential SM path</label>
          <input
            className={INPUT_CLS}
            value={(auth.credential_ref as string) || ""}
            onChange={(e) => onConfigChange({ ...config, kind: "http_api", auth: { ...auth, credential_ref: e.target.value } })}
            placeholder="projects/p/secrets/NAME/versions/latest"
            spellCheck={false}
          />
        </div>
      )}
      <div>
        <label className={LABEL_CLS}>Allowed operations (comma-separated; empty = all)</label>
        <input
          className={INPUT_CLS}
          value={(allowed || []).join(", ")}
          onChange={(e) => {
            const list = e.target.value.split(",").map((s) => s.trim()).filter(Boolean);
            onConfigChange({
              ...config,
              kind: "http_api",
              allowed_operations: list.length === 0 ? null : list,
            });
          }}
          placeholder="getPetById, findPetsByStatus"
        />
      </div>
    </div>
  );
}

// ---- code_exec ----

function CodeExecForm({ config, onConfigChange }: { config: Record<string, unknown>; onConfigChange: ConfigUpdater }) {
  const runtime = (config.runtime as string) || "python3.12";
  const timeout = (config.timeout_seconds as number) ?? 30;
  const memory = (config.memory_mb as number) ?? 256;
  const network = (config.network as string) || "none";
  const allowed = (config.allowed_modules as string[]) || [];

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className={LABEL_CLS}>Runtime</label>
          <select
            className={INPUT_CLS}
            value={runtime}
            onChange={(e) => onConfigChange({ ...config, kind: "code_exec", runtime: e.target.value })}
          >
            <option value="python3.12">python3.12</option>
            <option value="bash">bash</option>
          </select>
        </div>
        <div>
          <label className={LABEL_CLS}>Network</label>
          <select
            className={INPUT_CLS}
            value={network}
            onChange={(e) => onConfigChange({ ...config, kind: "code_exec", network: e.target.value })}
          >
            <option value="none">none</option>
            <option value="egress-only">egress-only</option>
          </select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className={LABEL_CLS}>Timeout (seconds)</label>
          <input
            className={INPUT_CLS}
            type="number"
            min={1}
            max={300}
            value={timeout}
            onChange={(e) =>
              onConfigChange({ ...config, kind: "code_exec", timeout_seconds: Number(e.target.value) })
            }
          />
        </div>
        <div>
          <label className={LABEL_CLS}>Memory (MB)</label>
          <input
            className={INPUT_CLS}
            type="number"
            min={32}
            max={4096}
            value={memory}
            onChange={(e) =>
              onConfigChange({ ...config, kind: "code_exec", memory_mb: Number(e.target.value) })
            }
          />
        </div>
      </div>
      <div>
        <label className={LABEL_CLS}>Allowed modules (comma-separated, network=none only)</label>
        <input
          className={INPUT_CLS}
          value={allowed.join(", ")}
          onChange={(e) => {
            const list = e.target.value.split(",").map((s) => s.trim()).filter(Boolean);
            onConfigChange({ ...config, kind: "code_exec", allowed_modules: list });
          }}
          placeholder="json, math, datetime"
        />
      </div>
    </div>
  );
}
