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
}

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
}

/** Chat API response body. */
export interface ChatResponse {
  text: string;
  tool_calls: ToolCall[];
  is_final: boolean;
}

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
