/** Shared TypeScript types for GClaw web app. */

/** Task status matching backend TaskStatus enum. */
export type TaskStatus =
  | "backlog"
  | "queued"
  | "in_progress"
  | "needs_approval"
  | "done"
  | "failed";

/** Task priority matching backend TaskPriority enum. */
export type TaskPriority = "high" | "medium" | "low";

/** Source of a board task. */
export interface TaskSource {
  type: "user" | "agent" | "cron";
  origin?: string;
}

/** Result of a completed task. */
export interface TaskResult {
  summary: string;
  artifacts: string[];
}

/** Board task matching the backend BoardTask model. */
export interface BoardTask {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  source: TaskSource;
  assignee: string;
  dependencies: string[];
  requires_approval: boolean;
  result?: TaskResult;
  created_at: string;
  updated_at: string;
  approved_at?: string | null;
  approved_by?: string | null;
  approval_note?: string | null;
  rejected_at?: string | null;
  rejection_note?: string | null;
}

/** Allowed user-driven status transitions (mirrors backend). */
export const USER_ALLOWED_TRANSITIONS: Record<TaskStatus, TaskStatus[]> = {
  backlog: ["queued"],
  queued: ["backlog"],
  needs_approval: ["queued", "failed"],
  failed: ["queued", "backlog"],
  in_progress: [],
  done: [],
};

/** Chat message in the UI. */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  tool_calls?: ToolCall[];
}

/** Tool call from agent response. */
export interface ToolCall {
  name: string;
  args: Record<string, unknown>;
}

/** Chat API request body. */
export interface ChatRequest {
  session_id: string;
  message: string;
  /** Optional — omit or null to hit the default (orchestrator). */
  agent_name?: string | null;
}

/** Chat API response body. */
export interface ChatResponse {
  text: string;
  tool_calls: ToolCall[];
  is_final: boolean;
}

/** Voice WebSocket message from client to server. */
export interface VoiceClientMessage {
  type: "audio" | "end";
  data?: string; // base64 PCM
}

/** Voice WebSocket message from server to client. */
export interface VoiceServerMessage {
  type: "audio" | "turn_complete" | "error";
  data?: string; // base64 PCM
  message?: string;
}

/** Voice connection state. */
export type VoiceState = "idle" | "connecting" | "listening" | "processing" | "error";

/** Kanban board column definition. */
export interface BoardColumn {
  status: TaskStatus;
  label: string;
  color: string;
}

/** Board columns configuration. */
export const BOARD_COLUMNS: BoardColumn[] = [
  { status: "backlog", label: "Backlog", color: "border-gray-500" },
  { status: "queued", label: "Queued", color: "border-blue-500" },
  { status: "in_progress", label: "In Progress", color: "border-yellow-500" },
  { status: "needs_approval", label: "Needs Approval", color: "border-orange-500" },
  { status: "done", label: "Done", color: "border-green-500" },
  { status: "failed", label: "Failed", color: "border-red-500" },
];

/** Agent info from the admin API. */
export interface AgentInfo {
  name: string;
  has_soul_overlay: boolean;
}

/** Soul file content. */
export interface SoulFile {
  name: string;
  content: string;
}

/** Heartbeat log entry. */
export interface HeartbeatLogEntry {
  id: string;
  context_summary: string;
  reasoning: string;
  actions_taken: string[];
  tasks_created: string[];
  timestamp: string;
}

/** Heartbeat status values (backend enum). */
export type HeartbeatStatus = "sent" | "ok-token" | "ok-empty" | "skipped" | "failed";

/** Wake reason values (backend enum). */
export type WakeReason =
  | "interval"
  | "manual"
  | "board-event"
  | "cron"
  | "hook"
  | "retry"
  | "other";

/** Heartbeat event from the in-process ring buffer. */
export interface HeartbeatEvent {
  agent_id: string;
  status: HeartbeatStatus;
  reason: WakeReason;
  duration_ms: number;
  preview: string;
  error: string | null;
  timestamp: string;
}

/** Per-agent heartbeat health snapshot. */
export interface AgentHealth {
  agent_id: string;
  last_event_at: string | null;
  last_status: HeartbeatStatus | null;
  last_reason: WakeReason | null;
  last_preview: string;
}

/** Aggregated heartbeat health response. */
export interface HeartbeatHealth {
  agents: AgentHealth[];
}

/** Skill definition from the backend. */
export interface SkillInfo {
  name: string;
  description: string;
  version: string;
  trigger: {
    mode: "auto" | "manual" | "both";
    contexts: string[];
    command: string | null;
  };
  config: Record<string, unknown>;
  tools_required: string[];
  agents_granted: string[];
  source: "builtin" | "imported" | "custom";
  instructions_path?: string | null;
  examples_path?: string | null;
}

/** Payload accepted by POST/PATCH /admin/skills. */
export interface SkillCreatePayload {
  name: string;
  description: string;
  version?: string;
  trigger?: {
    mode: "auto" | "manual" | "both";
    contexts: string[];
    command: string | null;
  };
  config?: Record<string, unknown>;
  tools_required?: string[];
  agents_granted?: string[];
  source?: "builtin" | "imported" | "custom";
  instructions_path?: string | null;
  examples_path?: string | null;
}

/** Memory entry from the backend. */
export interface MemoryEntry {
  fact: string;
  topic: string;
  update_time: string | null;
  score: number | null;
}

/** Schedule specification (tagged union). */
export type ScheduleSpec =
  | { kind: "at"; at: string }
  | { kind: "every"; every_ms: number; anchor_ms?: number | null }
  | { kind: "cron"; expr: string; tz?: string | null; stagger_ms?: number | null };

/** Payload specification (tagged union). */
export type PayloadSpec =
  | { kind: "system_event"; text: string }
  | {
      kind: "agent_turn";
      message: string;
      model?: string | null;
      timeout_seconds?: number | null;
      light_context?: boolean;
    };

/** Delivery specification (tagged union). */
export type DeliverySpec =
  | { mode: "none" }
  | {
      mode: "announce";
      transport?: string;
      channel?: string | null;
      to?: string | null;
      account_id?: string | null;
      best_effort?: boolean;
    }
  | { mode: "webhook"; url: string; best_effort?: boolean };

/** Failure-alert policy. */
export interface FailureAlert {
  after: number;
  cooldown_ms: number;
  channel?: string | null;
  to?: string | null;
  url?: string | null;
  mode?: "announce" | "webhook";
  transport?: string;
}

/** Announce transport registry info. */
export interface TransportInfo {
  transports: string[];
  default: string;
}

/** Cron job definition (matches backend structured model). */
export interface CronInfo {
  id: string;
  title: string;
  description: string;
  schedule: ScheduleSpec;
  payload: PayloadSpec;
  delivery: DeliverySpec;
  failure_alert: FailureAlert | null;
  wake_mode: "now" | "next-heartbeat";
  enabled: boolean;
  delete_after_run: boolean;
  mode: "auto" | "todo";
  status: "active" | "paused";
  assignee: string;
  task_priority: string;
  last_run: string | null;
  next_run: string | null;
  created_at: string;
  updated_at: string;
  consecutive_errors?: number;
  last_error?: string | null;
}

/** Discriminated union for kanban cards on the unified board. */
export type BoardItem =
  | { kind: "task"; task: BoardTask }
  | { kind: "cron"; cron: CronInfo };

/** Connection permission level. */
export type ConnectionPermission = "read" | "write" | "task" | "full";

/** Connection status. */
export type ConnectionStatus = "pending" | "active" | "rejected" | "revoked";

/** Cross-user connection record. */
export interface ConnectionInfo {
  id: string;
  from_user_id: string;
  to_user_id: string;
  status: ConnectionStatus;
  permission: ConnectionPermission;
  shared_channel: string;
  created_at: string;
  updated_at: string;
}

/** Request body for creating a connection. */
export interface ConnectionRequest {
  to_user_id: string;
  permission: ConnectionPermission;
}

/** Request body for creating a cross-user task. */
export interface CrossUserTaskRequest {
  connection_id: string;
  title: string;
  assignee: string;
  description?: string;
}

/** Onboarding step response from the API. */
export interface OnboardingStepResponse {
  step: string;
  message: string;
  completed: boolean;
  user_profile_preview?: string;
  /** @deprecated renamed to user_profile_preview */
  soul_preview?: string;
}

/** Onboarding status from the API. */
export interface OnboardingStatus {
  completed: boolean;
  current_step: string | null;
  progress: number;
}

// ---------- Model Catalog ----------

export type ProviderKind =
  | "openai"
  | "anthropic"
  | "google_gemini"
  | "google_vertex"
  | "openrouter"
  | "ollama"
  | "groq"
  | "together"
  | "custom_openai"
  | "anthropic_oauth";

export type ApiKeyKind = "literal" | "env" | "sm";

export interface ApiKeySpec {
  kind: ApiKeyKind;
  value: string;
}

export interface Provider {
  id: string;
  name: string;
  kind: ProviderKind;
  base_url: string | null;
  api_key: ApiKeySpec | null;
  default_headers: Record<string, string>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProviderSummary extends Provider {
  model_count: number;
}

export interface ProviderCreate {
  name: string;
  kind: ProviderKind;
  base_url?: string | null;
  api_key?: ApiKeySpec | null;
  default_headers?: Record<string, string>;
  enabled?: boolean;
}

export type ProviderUpdate = Partial<ProviderCreate>;

export interface WriteSecretResponse {
  name: string;
  path: string;
  version_id: string;
  created_secret: boolean;
}

export interface SMSecretSummary {
  name: string;
  path: string;
  latest_version_created_at: string | null;
}

export interface Capabilities {
  text: boolean;
  vision: boolean;
  tools: boolean;
  reasoning: boolean;
  streaming: boolean;
}

export interface ModelCost {
  input_per_mtok: number | null;
  output_per_mtok: number | null;
  cache_read_per_mtok: number | null;
  cache_write_per_mtok: number | null;
}

export interface ModelParams {
  temperature: number | null;
  top_p: number | null;
  max_tokens: number | null;
  thinking_budget: number | null;
  extra: Record<string, unknown>;
}

export interface CatalogModel {
  id: string;
  provider_id: string;
  model_id: string;
  display_name: string;
  enabled: boolean;
  context_window: number | null;
  max_output_tokens: number | null;
  capabilities: Capabilities;
  params: ModelParams;
  cost: ModelCost;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface ModelCreate {
  provider_id: string;
  model_id: string;
  display_name?: string;
  enabled?: boolean;
  context_window?: number | null;
  max_output_tokens?: number | null;
  capabilities?: Partial<Capabilities>;
  params?: Partial<ModelParams>;
  cost?: Partial<ModelCost>;
  notes?: string;
}

export type ModelUpdate = Partial<Omit<ModelCreate, "provider_id">>;

export interface PresetModel {
  model_id: string;
  display_name: string;
  context_window?: number;
  max_output_tokens?: number;
  capabilities?: Partial<Capabilities>;
}

export interface Presets {
  providers: Record<
    ProviderKind,
    { base_url_default: string | null; models: PresetModel[] }
  >;
}

export interface TestModelResult {
  ok: boolean;
  latency_ms: number;
  error: string | null;
  sample_response: string | null;
}

// ---------- Tool Catalog ----------

export type ToolKind = "builtin" | "mcp" | "http_api" | "code_exec";

export interface ToolRecord {
  id: string;
  name: string;
  enabled: boolean;
  kind: ToolKind;
  // Config is a discriminated union on `kind`; the UI treats it as
  // opaque metadata and delegates to the per-kind form component.
  config: Record<string, unknown>;
  credential_ref: string | null;
  created_at: string;
  updated_at: string;
}

export interface ToolCreateRequest {
  name: string;
  config: Record<string, unknown>;
  enabled?: boolean;
  credential_ref?: string | null;
}

export interface ToolUpdateRequest {
  name?: string;
  config?: Record<string, unknown>;
  enabled?: boolean;
  credential_ref?: string | null;
}

export interface TestToolResult {
  ok: boolean;
  latency_ms: number;
  error: string | null;
  sample_response: unknown;
}

// ---------- Usage / Observability ----------

export type UsageKind = "model" | "agent" | "skill" | "tool";

export interface UsageEvent {
  id: string;
  kind: UsageKind;
  name: string;
  timestamp: string;
  user_id: string | null;
  session_id: string | null;
  duration_ms: number;
  success: boolean;
  error: string | null;
  provider_id: string | null;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_usd: number | null;
  caller: string | null;
  metadata: Record<string, unknown>;
}

// ---------- Agent Admin ----------

export type ThinkingLevel =
  | "off"
  | "minimal"
  | "low"
  | "medium"
  | "high"
  | "xhigh"
  | "adaptive";

export interface AgentIdentity {
  display_name: string | null;
  emoji: string | null;
  avatar_url: string | null;
  description: string | null;
}

export interface AgentModelSpec {
  primary: string | null;
  fallbacks: string[];
  thinking: ThinkingLevel | null;
  params: Record<string, unknown>;
}

export interface AgentToolsSpec {
  profile: string | null;
  allow: string[];
  deny: string[];
  catalog_tool_ids: string[];
}

export interface AgentSubagentsSpec {
  allow: string[] | null;
}

export interface AgentHeartbeatConfig {
  enabled: boolean;
  every: string;
  prompt: string | null;
  session: string;
  isolated_session: boolean;
  light_context: boolean;
  timeout_seconds: number;
  ack_max_chars: number;
  active_hours: { start: string; end: string; timezone: string } | null;
  target: "none" | "last" | "channel";
  channel: string | null;
  include_reasoning: boolean;
}

export interface AgentOverride {
  agent_name: string;
  identity: AgentIdentity;
  model: AgentModelSpec;
  tools: AgentToolsSpec;
  subagents: AgentSubagentsSpec;
  skills: string[] | null;
  heartbeat: AgentHeartbeatConfig | null;
  system_prompt_override: string | null;
  body_override: string | null;
  soul_overlay: string | null;
  enabled: boolean;
  is_standalone: boolean;
  created_at: string;
  updated_at: string;
}

export interface EffectiveAgentConfig {
  name: string;
  identity: AgentIdentity;
  model: AgentModelSpec;
  tools: AgentToolsSpec;
  subagents: AgentSubagentsSpec;
  skills: string[] | null;
  heartbeat: AgentHeartbeatConfig | null;
  system_prompt: string;
  body: string;
  soul_overlay: string | null;
  is_standalone: boolean;
  has_baseline: boolean;
  has_override: boolean;
}

export interface AgentListEntry {
  name: string;
  display_name: string | null;
  description: string | null;
  has_override: boolean;
  enabled: boolean;
  is_standalone: boolean;
  model_ref: string | null;
  heartbeat_enabled: boolean;
  tools_profile: string | null;
}

export interface CreateAgentPayload {
  agent_name: string;
  display_name?: string;
  body: string;
  model?: Partial<AgentModelSpec>;
  tools?: Partial<AgentToolsSpec>;
  skills?: string[] | null;
  heartbeat?: Partial<AgentHeartbeatConfig>;
}

export const PROTECTED_AGENTS = [
  "orchestrator",
  "workspace-mgr",
  "dev-mgr",
  "home-mgr",
  "comms-mgr",
  "research-mgr",
] as const;

// ---------- Shared Context ----------

export interface ContextEntry {
  id: string;
  namespace: string;
  timestamp: string;
  created_by: string;
  content: string | null;
  blob_url: string | null;
  blob_mime: string | null;
  metadata: Record<string, unknown>;
  expires_at: string;
}

export interface ContextNamespaceSummary {
  namespace: string;
  count: number;
  latest_at: string | null;
}

export interface ContextBlobUrl {
  url: string;
  expires_in_seconds: number;
}

export interface UsageSummary {
  totals: {
    model: number;
    agent: number;
    skill: number;
    tool: number;
    total_cost_usd: number;
  };
  top: {
    models: Array<{
      name: string;
      count: number;
      tokens_in: number;
      tokens_out: number;
      cost_usd: number;
    }>;
    agents: Array<{
      name: string;
      count: number;
      avg_duration_ms: number;
      failure_rate: number;
    }>;
    skills: Array<{ name: string; count: number }>;
    tools: Array<{ name: string; count: number; failure_rate: number }>;
  };
  timeseries: Array<{
    hour_iso: string;
    model_count: number;
    agent_count: number;
    skill_count: number;
    tool_count: number;
    cost_usd: number;
  }>;
}
