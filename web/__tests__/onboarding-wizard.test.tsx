import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, it, expect, beforeEach } from "vitest";
import OnboardingPage from "@/app/onboarding/page";

const mockApi = {
  startOnboarding: vi.fn().mockResolvedValue({
    step: "introduction",
    message: "Welcome to GClaw!",
    completed: false,
  }),
  advanceOnboarding: vi.fn().mockResolvedValue({
    step: "communication_style",
    message: "How do you like to communicate?",
    completed: false,
  }),
  getOnboardingStatus: vi.fn(),
};

vi.mock("@/lib/api-client", () => ({
  useApiClient: () => mockApi,
}));

describe("OnboardingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi.startOnboarding.mockResolvedValue({
      step: "introduction",
      message: "Welcome to GClaw!",
      completed: false,
    });
    mockApi.advanceOnboarding.mockResolvedValue({
      step: "communication_style",
      message: "How do you like to communicate?",
      completed: false,
    });
  });

  it("renders intro step on load", async () => {
    render(<OnboardingPage />);
    await waitFor(() => {
      expect(screen.getByText("Welcome to GClaw!")).toBeDefined();
    });
  });

  it("advances step on user response", async () => {
    render(<OnboardingPage />);
    await waitFor(() => {
      expect(screen.getByText("Welcome to GClaw!")).toBeDefined();
    });

    const input = screen.getByPlaceholderText("Type your response...");
    const button = screen.getByText("Send");
    await userEvent.type(input, "I prefer casual communication");
    await userEvent.click(button);

    expect(mockApi.advanceOnboarding).toHaveBeenCalledWith(
      "I prefer casual communication",
    );
  });

  it("shows completion state when done", async () => {
    mockApi.startOnboarding.mockResolvedValue({
      step: "complete",
      message: "Done!",
      completed: true,
      user_profile_preview: "## Identity\nScott, product lead",
    });

    render(<OnboardingPage />);
    await waitFor(() => {
      expect(screen.getByText("You are all set!")).toBeDefined();
    });
    expect(screen.getByText("Start Chatting")).toBeDefined();
  });
});
