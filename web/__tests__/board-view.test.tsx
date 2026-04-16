/**
 * Tests for Board View components.
 *
 * Assertions updated for the phosphor-observatory redesign:
 *   - Priority rendered as a single-character glyph (H / M / L).
 *   - Counts rendered in parentheses and zero-padded: (00), (01), (02).
 *   - Assignee in lowercase "unassigned" when empty.
 *   - Empty column placeholder is "— empty —".
 *   - Loading state uses an inline "LOADING BOARD" label, not a spinner DOM.
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

const mockUnsubscribe = vi.fn();
const mockOnSnapshot = vi.fn();

vi.mock("firebase/firestore", () => ({
  getFirestore: vi.fn(() => ({})),
  collection: vi.fn(() => ({})),
  query: vi.fn((ref: unknown) => ref),
  onSnapshot: (...args: unknown[]) => mockOnSnapshot(...args),
}));

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

  it("renders priority as single-character glyph (H) for high", () => {
    render(<TaskCard task={sampleTask} />);
    expect(screen.getByText("H")).toBeInTheDocument();
  });

  it("renders priority as (M) for medium", () => {
    render(<TaskCard task={{ ...sampleTask, priority: "medium" }} />);
    expect(screen.getByText("M")).toBeInTheDocument();
  });

  it("renders priority as (L) for low", () => {
    render(<TaskCard task={{ ...sampleTask, priority: "low" }} />);
    expect(screen.getByText("L")).toBeInTheDocument();
  });

  it("renders assignee name", () => {
    render(<TaskCard task={sampleTask} />);
    expect(screen.getByText("alice")).toBeInTheDocument();
  });

  it("renders 'unassigned' when assignee is empty", () => {
    render(<TaskCard task={{ ...sampleTask, assignee: "" }} />);
    expect(screen.getByText(/unassigned/i)).toBeInTheDocument();
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
    render(
      <BoardColumn
        column={inProgressColumn}
        tasks={[]}
        draggedTask={null}
        onDragStart={() => {}}
        onDragEnd={() => {}}
        onDrop={() => {}}
      />,
    );
    expect(screen.getByText("In Progress")).toBeInTheDocument();
  });

  it("shows count (00) when no tasks", () => {
    render(
      <BoardColumn
        column={inProgressColumn}
        tasks={[]}
        draggedTask={null}
        onDragStart={() => {}}
        onDragEnd={() => {}}
        onDrop={() => {}}
      />,
    );
    expect(screen.getByText("(00)")).toBeInTheDocument();
  });

  it("shows empty placeholder when no tasks", () => {
    render(
      <BoardColumn
        column={inProgressColumn}
        tasks={[]}
        draggedTask={null}
        onDragStart={() => {}}
        onDragEnd={() => {}}
        onDrop={() => {}}
      />,
    );
    expect(screen.getByText(/— empty —/i)).toBeInTheDocument();
  });

  it("renders task cards and count when tasks are provided", () => {
    const tasks = [sampleTask, { ...sampleTask, id: "task-2", title: "Second task" }];
    render(
      <BoardColumn
        column={inProgressColumn}
        tasks={tasks}
        draggedTask={null}
        onDragStart={() => {}}
        onDragEnd={() => {}}
        onDrop={() => {}}
      />,
    );
    expect(screen.getByText("(02)")).toBeInTheDocument();
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

  it("shows a loading label before data arrives", () => {
    // Never call the snapshot callback — stays in loading state
    mockOnSnapshot.mockImplementation(() => mockUnsubscribe);

    render(<BoardView />);
    expect(screen.getByText(/loading board/i)).toBeInTheDocument();
  });

  it("renders an empty board with (00) counts in all columns", async () => {
    mockOnSnapshot.mockImplementation((_q: unknown, cb: (snap: unknown) => void) => {
      cb({ docs: [] });
      return mockUnsubscribe;
    });

    render(<BoardView />);

    await waitFor(() => {
      const countBadges = screen.getAllByText("(00)");
      // One per board column + the scheduled column
      expect(countBadges.length).toBeGreaterThanOrEqual(BOARD_COLUMNS.length);
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
      },
    );

    render(<BoardView />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load board tasks/i)).toBeInTheDocument();
    });
  });
});
