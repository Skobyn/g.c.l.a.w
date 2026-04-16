/**
 * Tests for Chat View components.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock Firebase
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

vi.mock("firebase/firestore", () => ({
  getFirestore: vi.fn(() => ({})),
}));

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

import { MessageList } from "@/components/chat/message-list";
import { MessageInput } from "@/components/chat/message-input";
import type { ChatMessage } from "@/types";

describe("MessageList", () => {
  it("renders messages with correct roles", () => {
    const messages: ChatMessage[] = [
      {
        id: "1",
        role: "user",
        content: "Hello there",
        timestamp: new Date(),
      },
      {
        id: "2",
        role: "assistant",
        content: "Hi! How can I help?",
        timestamp: new Date(),
      },
    ];

    render(<MessageList messages={messages} activeAgent="orchestrator" />);

    expect(screen.getByText("Hello there")).toBeInTheDocument();
    expect(screen.getByText(/How can I help/)).toBeInTheDocument();
  });

  it("renders empty state when no messages", () => {
    render(<MessageList messages={[]} activeAgent="orchestrator" />);
    expect(
      screen.getByText(/the line is open/i)
    ).toBeInTheDocument();
  });
});

describe("MessageInput", () => {
  it("calls onSend when submitting a message", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();

    render(<MessageInput onSend={onSend} disabled={false} />);

    const input = screen.getByPlaceholderText(/channel/i);
    await user.type(input, "Hello GClaw");
    await user.keyboard("{Enter}");

    expect(onSend).toHaveBeenCalledWith("Hello GClaw");
  });

  it("does not send empty messages", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();

    render(<MessageInput onSend={onSend} disabled={false} />);

    const input = screen.getByPlaceholderText(/channel/i);
    await user.keyboard("{Enter}");

    expect(onSend).not.toHaveBeenCalled();
  });

  it("disables input when disabled prop is true", () => {
    render(<MessageInput onSend={vi.fn()} disabled={true} />);

    const input = screen.getByPlaceholderText(/channel/i);
    expect(input).toBeDisabled();
  });
});
