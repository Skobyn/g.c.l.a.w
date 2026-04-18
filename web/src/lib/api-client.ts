/**
 * Typed HTTP client for the GClaw FastAPI backend.
 *
 * Automatically injects the Firebase ID token into every request.
 * All methods throw on non-OK responses.
 */

import { useMemo } from "react";
import { useAuth } from "@/contexts/auth-context";
import type {
  ChatRequest,
  ChatResponse,
  BoardTask,
  TaskStatus,
  TaskPriority,
  AgentInfo,
  HeartbeatLogEntry,
  SoulFile,
  SkillInfo,
  MemoryEntry,
  CronInfo,
  ConnectionInfo,
  ConnectionRequest,
  ConnectionPermission,
  CrossUserTaskRequest,
  OnboardingStepResponse,
  OnboardingStatus,
  HeartbeatEvent,
  HeartbeatHealth,
  TransportInfo,
  Provider,
  ProviderSummary,
  ProviderCreate,
  ProviderUpdate,
  CatalogModel,
  ModelCreate,
  ModelUpdate,
  Presets,
  TestModelResult,
  UsageEvent,
  UsageKind,
  UsageSummary,
  AgentListEntry,
  EffectiveAgentConfig,
  AgentOverride,
  CreateAgentPayload,
  ContextEntry,
  ContextNamespaceSummary,
  ContextBlobUrl,
  WriteSecretResponse,
  SMSecretSummary,
} from "@/types";

export class ApiClient {
  private baseUrl: string;
  private getToken: () => Promise<string | null>;

  constructor(baseUrl: string, getToken: () => Promise<string | null>) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.getToken = getToken;
  }

  /** Build headers with auth token. */
  private async headers(): Promise<Record<string, string>> {
    const token = await this.getToken();
    if (!token) {
      throw new Error("Not authenticated");
    }
    return {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    };
  }

  /** Generic request handler with error checking. */
  private async request<T>(
    path: string,
    options: RequestInit = {}
  ): Promise<T> {
    const hdrs = await this.headers();
    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers: { ...hdrs, ...(options.headers as Record<string, string>) },
    });

    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch {
        // ignore JSON parse errors
      }
      throw new Error(`API error ${response.status}: ${detail}`);
    }

    return response.json() as Promise<T>;
  }

  /** Convenience GET request. */
  async get<T>(path: string): Promise<T> {
    return this.request<T>(path);
  }

  /** Convenience POST request. */
  async post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  }

  /** Send a chat message and get the agent response.
   *
   * `agentName` is optional — omit it (or pass null) to hit the
   * default orchestrator runner. Pass an agent name like "intel" or
   * "content-scott" to talk directly to that agent.
   */
  async chat(
    sessionId: string,
    message: string,
    agentName?: string | null,
  ): Promise<ChatResponse> {
    const body: ChatRequest = {
      session_id: sessionId,
      message,
    };
    if (agentName) {
      body.agent_name = agentName;
    }
    return this.request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  /** End a chat session. `agentName` scopes which agent's session
   *  to end — matches the scope used when messages were sent.
   */
  async endSession(
    sessionId: string,
    agentName?: string | null,
  ): Promise<void> {
    const body: { session_id: string; agent_name?: string } = {
      session_id: sessionId,
    };
    if (agentName) {
      body.agent_name = agentName;
    }
    await this.request<void>("/chat/end", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  /** Load persisted chat history for a session + agent. Returns empty
   *  array when no session exists yet rather than erroring. */
  async getChatHistory(
    sessionId: string,
    agentName?: string | null,
    limit: number = 100,
  ): Promise<{
    session_id: string;
    agent_name: string;
    messages: Array<{ role: string; content: string; timestamp: string }>;
  }> {
    const params = new URLSearchParams({
      session_id: sessionId,
      limit: String(limit),
    });
    if (agentName) params.set("agent_name", agentName);
    return this.request("/chat/history?" + params.toString());
  }

  /** Fetch all board tasks for the authenticated user. */
  async getBoardTasks(): Promise<BoardTask[]> {
    return this.request<BoardTask[]>("/board/tasks");
  }

  /** Create a new board task. */
  async createBoardTask(body: {
    title: string;
    description?: string;
    assignee: string;
    priority?: TaskPriority;
    initial_status?: "backlog" | "queued";
    requires_approval?: boolean;
    dependencies?: string[];
  }): Promise<BoardTask> {
    return this.request<BoardTask>("/board/tasks", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  /** Move a task to a new status (subject to backend transition rules). */
  async moveTaskStatus(id: string, target: TaskStatus): Promise<BoardTask> {
    return this.request<BoardTask>(
      `/board/tasks/${encodeURIComponent(id)}/status`,
      { method: "POST", body: JSON.stringify({ target }) },
    );
  }

  /** Approve a needs_approval task → moves to queued. */
  async approveTask(id: string, note?: string): Promise<BoardTask> {
    return this.request<BoardTask>(
      `/board/tasks/${encodeURIComponent(id)}/approve`,
      { method: "POST", body: JSON.stringify(note ? { note } : {}) },
    );
  }

  /** Reject a needs_approval task → moves to failed. Note is required. */
  async rejectTask(id: string, note: string): Promise<BoardTask> {
    return this.request<BoardTask>(
      `/board/tasks/${encodeURIComponent(id)}/reject`,
      { method: "POST", body: JSON.stringify({ note }) },
    );
  }

  /** Health check (no auth required). */
  async healthCheck(): Promise<{ status: string }> {
    const response = await fetch(`${this.baseUrl}/health`);
    return response.json();
  }

  // --- Admin: Agents ---

  async getAgents(): Promise<AgentInfo[]> {
    return this.request<AgentInfo[]>("/admin/agents");
  }

  // --- Admin: Agents (rich CRUD) ---

  async listAgentsRich(): Promise<AgentListEntry[]> {
    return this.request<AgentListEntry[]>("/admin/agents");
  }

  async getAgentConfig(name: string): Promise<EffectiveAgentConfig> {
    return this.request<EffectiveAgentConfig>(
      `/admin/agents/${encodeURIComponent(name)}`,
    );
  }

  async getAgentOverride(name: string): Promise<AgentOverride | null> {
    const hdrs = await this.headers();
    const response = await fetch(
      `${this.baseUrl}/admin/agents/${encodeURIComponent(name)}/override`,
      { headers: hdrs },
    );
    if (response.status === 404) return null;
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch {
        // ignore
      }
      throw new Error(`API error ${response.status}: ${detail}`);
    }
    return response.json() as Promise<AgentOverride>;
  }

  async getAgentBaseline(
    name: string,
  ): Promise<{ body: string; has_baseline: boolean }> {
    return this.request<{ body: string; has_baseline: boolean }>(
      `/admin/agents/${encodeURIComponent(name)}/baseline`,
    );
  }

  async createAgent(body: CreateAgentPayload): Promise<AgentOverride> {
    return this.request<AgentOverride>("/admin/agents", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async updateAgent(
    name: string,
    patch: Partial<AgentOverride>,
  ): Promise<AgentOverride> {
    return this.request<AgentOverride>(
      `/admin/agents/${encodeURIComponent(name)}`,
      { method: "PATCH", body: JSON.stringify(patch) },
    );
  }

  async deleteAgent(
    name: string,
    force = false,
  ): Promise<{ deleted: boolean; reverted_to_baseline: boolean }> {
    const q = force ? "?force=true" : "";
    return this.request<{ deleted: boolean; reverted_to_baseline: boolean }>(
      `/admin/agents/${encodeURIComponent(name)}${q}`,
      { method: "DELETE" },
    );
  }

  async getTransports(): Promise<TransportInfo> {
    return this.request<TransportInfo>("/admin/transports");
  }

  // --- Admin: Heartbeat Logs ---

  async getHeartbeatLogs(limit = 20): Promise<HeartbeatLogEntry[]> {
    return this.request<HeartbeatLogEntry[]>(`/admin/heartbeat-logs?limit=${limit}`);
  }

  async getHeartbeatEvents(
    limit = 50,
    agentId?: string,
  ): Promise<HeartbeatEvent[]> {
    let url = `/admin/heartbeat/events?limit=${limit}`;
    if (agentId) url += `&agent_id=${encodeURIComponent(agentId)}`;
    return this.request<HeartbeatEvent[]>(url);
  }

  async getHeartbeatHealth(): Promise<HeartbeatHealth> {
    return this.request<HeartbeatHealth>("/admin/heartbeat/health");
  }

  async triggerHeartbeat(
    agentId: string,
  ): Promise<{ event: HeartbeatEvent | null }> {
    return this.post(
      `/admin/heartbeat/trigger?agent_id=${encodeURIComponent(agentId)}`,
      {},
    );
  }

  // --- Admin: Soul Files ---

  async getSoulFile(name: string): Promise<SoulFile> {
    return this.request<SoulFile>(`/admin/soul/${name}`);
  }

  async updateSoulFile(name: string, content: string): Promise<{ status: string }> {
    return this.request<{ status: string }>(`/admin/soul/${name}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    });
  }

  // --- Admin: User Profile ---

  async getUserProfile(): Promise<{ content: string }> {
    return this.request<{ content: string }>("/admin/user-profile");
  }

  async updateUserProfile(
    content: string,
  ): Promise<{ status: string; bytes: number }> {
    return this.request<{ status: string; bytes: number }>("/admin/user-profile", {
      method: "PUT",
      body: JSON.stringify({ content }),
    });
  }

  // --- Admin: Skills ---

  async getSkills(): Promise<SkillInfo[]> {
    return this.request<SkillInfo[]>("/admin/skills");
  }

  async getSkill(name: string): Promise<SkillInfo> {
    return this.request<SkillInfo>(`/admin/skills/${name}`);
  }

  // --- Admin: Memory ---

  async searchMemories(query: string, agentId?: string): Promise<MemoryEntry[]> {
    let url = `/admin/memory/search?q=${encodeURIComponent(query)}`;
    if (agentId) url += `&agent_id=${encodeURIComponent(agentId)}`;
    return this.request<MemoryEntry[]>(url);
  }

  async listMemories(agentId?: string): Promise<MemoryEntry[]> {
    let url = "/admin/memory/list";
    if (agentId) url += `?agent_id=${encodeURIComponent(agentId)}`;
    return this.request<MemoryEntry[]>(url);
  }

  async deleteMemory(fact: string, agentId?: string): Promise<void> {
    await this.request<{ status: string }>("/admin/memory/delete", {
      method: "POST",
      body: JSON.stringify({ fact, agent_id: agentId }),
    });
  }

  // --- Admin: Crons ---

  async getCrons(): Promise<CronInfo[]> {
    return this.request<CronInfo[]>("/admin/crons");
  }

  async listCrons(): Promise<CronInfo[]> {
    return this.request<CronInfo[]>("/crons");
  }

  async updateCron(
    cronId: string,
    body: Partial<CronInfo>,
  ): Promise<CronInfo> {
    return this.request<CronInfo>(`/crons/${encodeURIComponent(cronId)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  }

  async deleteCron(cronId: string): Promise<void> {
    const hdrs = await this.headers();
    const response = await fetch(
      `${this.baseUrl}/crons/${encodeURIComponent(cronId)}`,
      { method: "DELETE", headers: hdrs },
    );
    if (!response.ok && response.status !== 204) {
      let detail = response.statusText;
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch {
        /* ignore */
      }
      throw new Error(`API error ${response.status}: ${detail}`);
    }
  }

  async toggleCron(cronId: string): Promise<CronInfo> {
    return this.request<CronInfo>(`/admin/crons/${cronId}/toggle`, {
      method: "POST",
    });
  }

  async triggerCron(cronId: string): Promise<{ status: string; task_id: string }> {
    return this.request<{ status: string; task_id: string }>(`/crons/${cronId}/trigger`, {
      method: "POST",
    });
  }

  // --- Connections ---

  async listConnections(): Promise<ConnectionInfo[]> {
    return this.get<ConnectionInfo[]>("/connections");
  }

  async listIncomingRequests(): Promise<ConnectionInfo[]> {
    return this.get<ConnectionInfo[]>("/connections/incoming");
  }

  async requestConnection(body: ConnectionRequest): Promise<ConnectionInfo> {
    return this.post<ConnectionInfo>("/connections/request", body);
  }

  async acceptConnection(connectionId: string): Promise<ConnectionInfo> {
    return this.post<ConnectionInfo>(`/connections/${connectionId}/accept`);
  }

  async rejectConnection(connectionId: string): Promise<ConnectionInfo> {
    return this.post<ConnectionInfo>(`/connections/${connectionId}/reject`);
  }

  async revokeConnection(connectionId: string): Promise<ConnectionInfo> {
    return this.post<ConnectionInfo>(`/connections/${connectionId}/revoke`);
  }

  async updateConnectionPermission(
    connectionId: string,
    permission: ConnectionPermission,
  ): Promise<ConnectionInfo> {
    return this.post<ConnectionInfo>(
      `/connections/${connectionId}/permission`,
      { permission },
    );
  }

  async createCrossUserTask(body: CrossUserTaskRequest): Promise<BoardTask> {
    return this.post<BoardTask>("/connections/task", body);
  }

  // --- Onboarding ---

  async startOnboarding(): Promise<OnboardingStepResponse> {
    return this.post<OnboardingStepResponse>("/onboarding/start");
  }

  async advanceOnboarding(response: string): Promise<OnboardingStepResponse> {
    return this.post<OnboardingStepResponse>("/onboarding/advance", {
      response,
    });
  }

  async getOnboardingStatus(): Promise<OnboardingStatus> {
    return this.get<OnboardingStatus>("/onboarding/status");
  }

  // --- Admin: Model Catalog ---

  async listProviders(): Promise<ProviderSummary[]> {
    return this.get<ProviderSummary[]>("/admin/model-providers");
  }

  async getProvider(id: string): Promise<Provider> {
    return this.get<Provider>(`/admin/model-providers/${encodeURIComponent(id)}`);
  }

  async createProvider(body: ProviderCreate): Promise<Provider> {
    return this.request<Provider>("/admin/model-providers", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async updateProvider(id: string, body: ProviderUpdate): Promise<Provider> {
    return this.request<Provider>(
      `/admin/model-providers/${encodeURIComponent(id)}`,
      { method: "PATCH", body: JSON.stringify(body) },
    );
  }

  async deleteProvider(id: string): Promise<void> {
    await this.request<{ deleted: boolean }>(
      `/admin/model-providers/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    );
  }

  async listModels(providerId?: string): Promise<CatalogModel[]> {
    const q = providerId
      ? `?provider_id=${encodeURIComponent(providerId)}`
      : "";
    return this.get<CatalogModel[]>(`/admin/models${q}`);
  }

  async getModel(id: string): Promise<CatalogModel> {
    return this.get<CatalogModel>(`/admin/models/${encodeURIComponent(id)}`);
  }

  async createModel(body: ModelCreate): Promise<CatalogModel> {
    return this.request<CatalogModel>("/admin/models", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async updateModel(id: string, body: ModelUpdate): Promise<CatalogModel> {
    return this.request<CatalogModel>(
      `/admin/models/${encodeURIComponent(id)}`,
      { method: "PATCH", body: JSON.stringify(body) },
    );
  }

  async deleteModel(id: string): Promise<void> {
    await this.request<{ deleted: boolean }>(
      `/admin/models/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    );
  }

  async testModel(id: string): Promise<TestModelResult> {
    return this.post<TestModelResult>(
      `/admin/models/${encodeURIComponent(id)}/test`,
      {},
    );
  }

  async getPresets(): Promise<Presets> {
    return this.get<Presets>("/admin/model-presets");
  }

  // --- Admin: Secret Manager (UI-driven secret storage) ---

  async writeSecret(body: {
    name: string;
    value: string;
    create_if_missing?: boolean;
  }): Promise<WriteSecretResponse> {
    return this.post<WriteSecretResponse>("/admin/secrets", body);
  }

  async rotateSecret(
    name: string,
    value: string,
  ): Promise<WriteSecretResponse> {
    return this.post<WriteSecretResponse>(
      `/admin/secrets/${encodeURIComponent(name)}/rotate`,
      { value },
    );
  }

  async listSecrets(): Promise<{ secrets: SMSecretSummary[] }> {
    return this.get<{ secrets: SMSecretSummary[] }>("/admin/secrets");
  }

  async writeOAuthSecret(body: {
    name: string;
    access_token: string;
    refresh_token: string;
    expires_in_seconds?: number;
  }): Promise<WriteSecretResponse> {
    return this.post<WriteSecretResponse>("/admin/secrets/oauth", body);
  }

  async refreshOAuthNow(
    name: string,
  ): Promise<{ refreshed: boolean; expires_at: string | null }> {
    return this.post<{ refreshed: boolean; expires_at: string | null }>(
      `/admin/secrets/oauth/${encodeURIComponent(name)}/refresh-now`,
      {},
    );
  }

  // --- Admin: Usage / Observability ---

  async getUsageEvents(opts?: {
    kind?: UsageKind;
    limit?: number;
    since?: string;
  }): Promise<UsageEvent[]> {
    const params = new URLSearchParams();
    if (opts?.kind) params.set("kind", opts.kind);
    if (opts?.limit !== undefined) params.set("limit", String(opts.limit));
    if (opts?.since) params.set("since", opts.since);
    const q = params.toString();
    return this.get<UsageEvent[]>(
      `/admin/usage/events${q ? `?${q}` : ""}`,
    );
  }

  async getUsageSummary(opts?: {
    since?: string;
    topN?: number;
  }): Promise<UsageSummary> {
    const params = new URLSearchParams();
    if (opts?.since) params.set("since", opts.since);
    if (opts?.topN !== undefined) params.set("top_n", String(opts.topN));
    const q = params.toString();
    return this.get<UsageSummary>(
      `/admin/usage/summary${q ? `?${q}` : ""}`,
    );
  }

  // --- Admin: Shared Context ---

  async listContextNamespaces(): Promise<ContextNamespaceSummary[]> {
    return this.get<ContextNamespaceSummary[]>("/admin/context/namespaces");
  }

  async listContextEntries(
    namespace: string,
    opts?: { limit?: number; since?: string },
  ): Promise<ContextEntry[]> {
    const params = new URLSearchParams();
    params.set("namespace", namespace);
    if (opts?.limit !== undefined) params.set("limit", String(opts.limit));
    if (opts?.since) params.set("since", opts.since);
    return this.get<ContextEntry[]>(`/admin/context?${params.toString()}`);
  }

  async getContextEntry(id: string): Promise<ContextEntry> {
    return this.get<ContextEntry>(
      `/admin/context/${encodeURIComponent(id)}`,
    );
  }

  async getContextBlobUrl(id: string): Promise<ContextBlobUrl> {
    return this.get<ContextBlobUrl>(
      `/admin/context/${encodeURIComponent(id)}/blob`,
    );
  }

  async deleteContextEntry(id: string): Promise<void> {
    await this.request<{ deleted: boolean }>(
      `/admin/context/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    );
  }

  async createContextEntry(body: {
    namespace: string;
    content: string;
    metadata?: Record<string, unknown>;
  }): Promise<ContextEntry> {
    return this.request<ContextEntry>("/admin/context", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  async installPresets(
    providerId: string,
    modelIds: string[],
  ): Promise<{ created: CatalogModel[] }> {
    return this.post<{ created: CatalogModel[] }>(
      `/admin/model-providers/${encodeURIComponent(providerId)}/install-presets`,
      { model_ids: modelIds },
    );
  }
}

/**
 * Create a pre-configured ApiClient instance.
 * Pass the getIdToken function from useAuth().
 */
export function createApiClient(
  getToken: () => Promise<string | null>
): ApiClient {
  const baseUrl =
    process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
  return new ApiClient(baseUrl, getToken);
}

/**
 * React hook that returns a stable ApiClient instance for the current user.
 * Must be used within an AuthProvider.
 */
export function useApiClient(): ApiClient {
  const { getIdToken } = useAuth();
  return useMemo(() => createApiClient(getIdToken), [getIdToken]);
}
