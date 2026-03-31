/**
 * Tests for Board View components.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

// Mock Firebase auth
vi.mock("firebase/auth", () => ({
  getAuth: vi.fn(() => ({})),
  GoogleAuthProvider: vi.fn(),
  onAuthStateChanged: vi.fn((_auth: unknown, cb: (u: unknown) => void) => {
    cb({ uid: "test_user", getIdToken: vi.fn().mockResolvedValue("token") });
    return vi.fn();
  }),
  signInWithPopup: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock("firebase/app", () => ({
  initializeApp: vi.fn(() => ({})),
  getApps: vi.fn(() => []),
}));

// Mock Firestore — onSnapshot will be overridden per test
const mockUnsubscribe = vi.fn();
const mockOnSnapshot = vi.fn();

vi.mock("firebase/firestore", () => ({
  getFirestore: vi.fn(() => ({})),
  collection: vi.fn(() => ({})),
  query: vi.fn((ref: unknown) => ref),
  onSnapshot: (...args: unknown[]) => mockOnSnapshot(...args),
}));

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

import { TaskCard } from "@/components/board/task-card";
import { BoardColumn } from "@/components/board/board-column";
import { BoardView } from "@/components/board/board-view";
import { BOARD_COLUMNS } from "@/types";
import type { BoardTask, BoardColumn as BoardColumnType } from "@/types";

// ─── TaskCard ────────────────────────────────────────────────────────────────

const sampleTask: BoardTask = {
  id: "task-1",
  title: "Fix the login bug",
  description: "Users cannot log in on Safari",
  status: "in_progress",
  priority: "high",
  source: { type: "user" },
  assignee: "alice",
  dependencies: [],
  requires_approval: false,
  created_at: "2026-03-30T00:00:00Z",
  updated_at: "2026-03-30T00:00:00Z",
};

describe("TaskCard", () => {
  it("renders task title", () => {
    render(<TaskCard task={sampleTask} />);
    expect(screen.getByText("Fix the login bug")).toBeInTheDocument();
  });

  it("renders priority badge with correct label", () => {
    render(<TaskCard task={sampleTask} />);
    expect(screen.getByText("high")).toBeInTheDocument();
  });

  it("renders assignee name", () => {
    render(<TaskCard task={sampleTask} />);
    expect(screen.getByText("alice")).toBeInTheDocument();
  });

  it("renders 'Unassigned' when assignee is empty", () => {
    render(<TaskCard task={{ ...sampleTask, assignee: "" }} />);
    expect(screen.getByText("Unassigned")).toBeInTheDocument();
  });

  it("renders status indicator with correct aria-label", () => {
    render(<TaskCard task={sampleTask} />);
    expect(screen.getByLabelText("Status: in_progress")).toBeInTheDocument();
  });

  it("applies red badge class for high priority", () => {
    render(<TaskCard task={sampleTask} />);
    const badge = screen.getByText("high");
    expect(badge.className).toMatch(/red/);
  });

  it("applies yellow badge class for medium priority", () => {
    render(<TaskCard task={{ ...sampleTask, priority: "medium" }} />);
    const badge = screen.getByText("medium");
    expect(badge.className).toMatch(/yellow/);
  });

  it("applies green badge class for low priority", () => {
    render(<TaskCard task={{ ...sampleTask, priority: "low" }} />);
    const badge = screen.getByText("low");
    expect(badge.className).toMatch(/green/);
  });
});

// ─── BoardColumn ─────────────────────────────────────────────────────────────

const inProgressColumn: BoardColumnType = {
  status: "in_progress",
  label: "In Progress",
  color: "border-yellow-500",
};

describe("BoardColumn", () => {
  it("renders the column label", () => {
    render(<BoardColumn column={inProgressColumn} tasks={[]} />);
    expect(screen.getByText("In Progress")).toBeInTheDocument();
  });

  it("shows count of 0 when no tasks", () => {
    render(<BoardColumn column={inProgressColumn} tasks={[]} />);
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("shows empty state message when no tasks", () => {
    render(<BoardColumn column={inProgressColumn} tasks={[]} />);
    expect(screen.getByText(/no tasks/i)).toBeInTheDocument();
  });

  it("renders task cards and count when tasks are provided", () => {
    const tasks = [sampleTask, { ...sampleTask, id: "task-2", title: "Second task" }];
    render(<BoardColumn column={inProgressColumn} tasks={tasks} />);
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("Fix the login bug")).toBeInTheDocument();
    expect(screen.getByText("Second task")).toBeInTheDocument();
  });
});

// ─── BoardView ───────────────────────────────────────────────────────────────

describe("BoardView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders all board columns", async () => {
    // Simulate an immediate snapshot with no tasks
    mockOnSnapshot.mockImplementation((_q: unknown, cb: (snap: unknown) => void) => {
      cb({ docs: [] });
      return mockUnsubscribe;
    });

    render(<BoardView />);

    await waitFor(() => {
      for (const col of BOARD_COLUMNS) {
        expect(screen.getByText(col.label)).toBeInTheDocument();
      }
    });
  });

  it("shows loading spinner before data arrives", () => {
    // Never call the snapshot callback — stays in loading state
    mockOnSnapshot.mockImplementation(() => mockUnsubscribe);

    render(<BoardView />);
    // The spinner has no text; look for the spin class container instead
    const spinner = document.querySelector(".animate-spin");
    expect(spinner).not.toBeNull();
  });

  it("renders an empty board with zero counts in all columns", async () => {
    mockOnSnapshot.mockImplementation((_q: unknown, cb: (snap: unknown) => void) => {
      cb({ docs: [] });
      return mockUnsubscribe;
    });

    render(<BoardView />);

    await waitFor(() => {
      // Each column should show count 0
      const countBadges = screen.getAllByText("0");
      expect(countBadges.length).toBe(BOARD_COLUMNS.length);
    });
  });

  it("groups tasks by status into the correct column", async () => {
    const backlogTask: BoardTask = {
      ...sampleTask,
      id: "t1",
      title: "Backlog item",
      status: "backlog",
    };
    const doneTask: BoardTask = {
      ...sampleTask,
      id: "t2",
      title: "Completed work",
      status: "done",
    };

    mockOnSnapshot.mockImplementation((_q: unknown, cb: (snap: unknown) => void) => {
      cb({
        docs: [
          { id: backlogTask.id, data: () => ({ ...backlogTask }) },
          { id: doneTask.id, data: () => ({ ...doneTask }) },
        ],
      });
      return mockUnsubscribe;
    });

    render(<BoardView />);

    await waitFor(() => {
      expect(screen.getByText("Backlog item")).toBeInTheDocument();
      expect(screen.getByText("Completed work")).toBeInTheDocument();
    });
  });

  it("shows error message when Firestore fails", async () => {
    mockOnSnapshot.mockImplementation(
      (_q: unknown, _cb: unknown, errCb: (e: Error) => void) => {
        errCb(new Error("permission-denied"));
        return mockUnsubscribe;
      }
    );

    render(<BoardView />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load board tasks/i)).toBeInTheDocument();
    });
  });
});
