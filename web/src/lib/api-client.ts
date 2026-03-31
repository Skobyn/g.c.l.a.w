/**
 * Typed HTTP client for the GClaw FastAPI backend.
 *
 * Automatically injects the Firebase ID token into every request.
 * All methods throw on non-OK responses.
 */

import type { ChatRequest, ChatResponse, BoardTask } from "@/types";

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
