import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import ConnectionsPage from "@/app/connections/page";

const mockApi = {
  listConnections: vi.fn().mockResolvedValue([]),
  listIncomingRequests: vi.fn().mockResolvedValue([]),
  requestConnection: vi.fn().mockResolvedValue({ id: "c1" }),
  acceptConnection: vi.fn(),
  rejectConnection: vi.fn(),
  revokeConnection: vi.fn(),
  updateConnectionPermission: vi.fn(),
};

vi.mock("@/lib/api-client", () => ({
  useApiClient: () => mockApi,
}));

vi.mock("@/components/layout/app-shell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

describe("ConnectionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi.listConnections.mockResolvedValue([]);
    mockApi.listIncomingRequests.mockResolvedValue([]);
  });

  it("renders all sections", async () => {
    render(<ConnectionsPage />);
    expect(screen.getByText("Connections")).toBeDefined();
    expect(screen.getByText("Connect with a User")).toBeDefined();
    expect(screen.getByText("Incoming Requests")).toBeDefined();
    expect(screen.getByText("Active Connections")).toBeDefined();
  });

  it("shows empty state for no connections", async () => {
    render(<ConnectionsPage />);
    await waitFor(() => {
      expect(screen.getByText("No active connections.")).toBeDefined();
    });
  });

  it("sends connection request on form submit", async () => {
    render(<ConnectionsPage />);
    const input = screen.getByPlaceholderText("Enter user ID");
    const button = screen.getByText("Send Request");

    await userEvent.type(input, "other_user");
    await userEvent.click(button);

    expect(mockApi.requestConnection).toHaveBeenCalledWith({
      to_user_id: "other_user",
      permission: "read",
    });
  });
});
