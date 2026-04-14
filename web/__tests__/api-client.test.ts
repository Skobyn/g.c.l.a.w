/**
 * Tests for the API client.
 *
 * Mocks fetch globally to verify request construction, auth headers,
 * and response handling.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock Firebase modules
vi.mock("firebase/auth", () => ({
  getAuth: vi.fn(() => ({})),
  GoogleAuthProvider: vi.fn(),
  onAuthStateChanged: vi.fn(),
  signInWithPopup: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock("firebase/app", () => ({
  initializeApp: vi.fn(() => ({})),
  getApps: vi.fn(() => []),
}));

vi.mock("firebase/firestore", () => ({
  getFirestore: vi.fn(() => ({})),
}));

import { ApiClient } from "@/lib/api-client";

describe("ApiClient", () => {
  let client: ApiClient;
  const mockGetToken = vi.fn<() => Promise<string | null>>();

  beforeEach(() => {
    client = new ApiClient("http://localhost:8000", mockGetToken);
    mockGetToken.mockResolvedValue("test_token_123");
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends chat request with auth header", async () => {
    const mockResponse = {
      ok: true,
      json: vi.fn().mockResolvedValue({
        text: "Hello!",
        tool_calls: [],
        is_final: true,
      }),
    };
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

    const result = await client.chat("sess_1", "Hello");

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/chat",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "Content-Type": "application/json",
          Authorization: "Bearer test_token_123",
        }),
        body: JSON.stringify({
          session_id: "sess_1",
          message: "Hello",
        }),
      })
    );
    expect(result.text).toBe("Hello!");
  });

  it("fetches board tasks with auth header", async () => {
    const mockResponse = {
      ok: true,
      json: vi.fn().mockResolvedValue([
        { id: "task_1", title: "Test task", status: "queued" },
      ]),
    };
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

    const tasks = await client.getBoardTasks();

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/board/tasks",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer test_token_123",
        }),
      })
    );
    expect(tasks).toHaveLength(1);
    expect(tasks[0].title).toBe("Test task");
  });

  it("creates a board task", async () => {
    const mockResponse = {
      ok: true,
      json: vi.fn().mockResolvedValue({
        id: "task_new",
        title: "New task",
        status: "backlog",
      }),
    };
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

    const task = await client.createBoardTask({
      title: "New task",
      assignee: "workspace-mgr",
    });

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/board/tasks",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          title: "New task",
          assignee: "workspace-mgr",
        }),
      })
    );
    expect(task.title).toBe("New task");
  });

  it("throws on non-ok response", async () => {
    const mockResponse = {
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: vi.fn().mockResolvedValue({ detail: "Something broke" }),
    };
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse);

    await expect(client.chat("sess_1", "Hello")).rejects.toThrow();
  });

  it("throws when no auth token available", async () => {
    mockGetToken.mockResolvedValue(null);

    await expect(client.chat("sess_1", "Hello")).rejects.toThrow(
      "Not authenticated"
    );
  });
});
