/**
 * Typed HTTP client for the GClaw FastAPI backend.
 *
 * Automatically injects the Firebase ID token into every request.
 * All methods throw on non-OK responses.
 */

import type {
  ChatRequest,
  ChatResponse,
  BoardTask,
  AgentInfo,
  HeartbeatLogEntry,
  SoulFile,
  SkillInfo,
  MemoryEntry,
  CronInfo,
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

  /** Send a chat message and get the agent response. */
  async chat(sessionId: string, message: string): Promise<ChatResponse> {
    const body: ChatRequest = {
      session_id: sessionId,
      message,
    };
    return this.request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  /** Fetch all board tasks for the authenticated user. */
  async getBoardTasks(): Promise<BoardTask[]> {
    return this.request<BoardTask[]>("/board/tasks");
  }

  /** Create a new board task. */
  async createBoardTask(
    title: string,
    assignee: string,
    description?: string,
    priority?: string
  ): Promise<BoardTask> {
    const body: Record<string, string> = { title, assignee };
    if (description) body.description = description;
    if (priority) body.priority = priority;
    return this.request<BoardTask>("/board/tasks", {
      method: "POST",
      body: JSON.stringify(body),
    });
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

  // --- Admin: Heartbeat Logs ---

  async getHeartbeatLogs(limit = 20): Promise<HeartbeatLogEntry[]> {
    return this.request<HeartbeatLogEntry[]>(`/admin/heartbeat-logs?limit=${limit}`);
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
