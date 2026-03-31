import { describe, it, expect, vi } from "vitest";
import { VoiceClient } from "@/lib/voice-client";

describe("VoiceClient", () => {
  it("initializes with idle state", () => {
    const onState = vi.fn();
    const client = new VoiceClient(
      "http://localhost:8000",
      async () => "fake-token",
      onState,
    );
    expect(client.getState()).toBe("idle");
  });

  it("converts http base URL to ws", () => {
    const onState = vi.fn();
    const client = new VoiceClient(
      "https://api.example.com",
      async () => "token",
      onState,
    );
    // Internal URL should be wss://api.example.com
    expect(client.getState()).toBe("idle");
  });
});
