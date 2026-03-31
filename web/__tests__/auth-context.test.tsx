/**
 * Tests for AuthContext provider.
 *
 * Mocks Firebase auth to test context behavior without a real Firebase project.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock Firebase modules before importing components
const mockOnAuthStateChanged = vi.fn();
const mockSignInWithPopup = vi.fn();
const mockSignOut = vi.fn();

vi.mock("firebase/auth", () => ({
  getAuth: vi.fn(() => ({})),
  GoogleAuthProvider: vi.fn(),
  onAuthStateChanged: (...args: unknown[]) => mockOnAuthStateChanged(...args),
  signInWithPopup: (...args: unknown[]) => mockSignInWithPopup(...args),
  signOut: (...args: unknown[]) => mockSignOut(...args),
}));

vi.mock("firebase/app", () => ({
  initializeApp: vi.fn(() => ({})),
  getApps: vi.fn(() => []),
}));

vi.mock("firebase/firestore", () => ({
  getFirestore: vi.fn(() => ({})),
}));

import { AuthProvider, useAuth } from "@/contexts/auth-context";

function TestConsumer() {
  const { user, loading, signInWithGoogle, signOut } = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="user">{user ? user.uid : "null"}</span>
      <button onClick={signInWithGoogle}>Sign In</button>
      <button onClick={signOut}>Sign Out</button>
    </div>
  );
}

describe("AuthProvider", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("starts in loading state", () => {
    // Don't call the callback yet
    mockOnAuthStateChanged.mockReturnValue(vi.fn());

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    expect(screen.getByTestId("loading").textContent).toBe("true");
    expect(screen.getByTestId("user").textContent).toBe("null");
  });

  it("updates user when auth state changes", async () => {
    mockOnAuthStateChanged.mockImplementation((_auth: unknown, callback: (user: unknown) => void) => {
      // Simulate async auth state resolution
      setTimeout(() => callback({ uid: "test_uid_123", getIdToken: vi.fn() }), 0);
      return vi.fn();
    });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("loading").textContent).toBe("false");
      expect(screen.getByTestId("user").textContent).toBe("test_uid_123");
    });
  });

  it("sets user to null when not authenticated", async () => {
    mockOnAuthStateChanged.mockImplementation((_auth: unknown, callback: (user: null) => void) => {
      setTimeout(() => callback(null), 0);
      return vi.fn();
    });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("loading").textContent).toBe("false");
      expect(screen.getByTestId("user").textContent).toBe("null");
    });
  });
});
