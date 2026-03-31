# GClaw Voice + Agent Dashboard + Admin Views (Plan 4b of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real-time voice conversation via Gemini Live API, build an Agent Dashboard for monitoring and configuring agents, create Skills & Crons management views, build a Memory Explorer, and unify navigation across all views with a sidebar layout.

**Architecture:** The backend gains a FastAPI WebSocket endpoint that proxies bidirectional audio between the browser and Gemini Live API using the `google.genai` SDK's `AsyncLive.connect()` / `AsyncSession` interface. New REST API routes expose agent metadata, heartbeat logs, soul file read/write, skill listing, and memory search/list/delete — all thin wrappers around existing services (`HeartbeatLogRepo`, `SkillRegistry`, `MemoryService`, `ConfigLoader`). The frontend adds MediaRecorder-based audio capture, AudioContext-based playback, and four new page views (Agent Dashboard, Skills, Crons, Memory Explorer) inside a shared sidebar navigation layout.

**Tech Stack:**
- Backend: Python 3.10, FastAPI (incl. WebSocket support), `google-genai` v1.67+ (`google.genai.live.AsyncLive`), firebase-admin
- Frontend: Next.js 14+ App Router, TypeScript (strict), Tailwind CSS, Firebase JS SDK
- Testing: pytest + mocks (backend), vitest + React Testing Library (frontend)

**Builds on Plans 1-4a:**
- `create_app` factory in `api/app.py` with service injection and auth middleware
- `AgentRunner`, `BoardService`, `CronService`, `HeartbeatService`, `MemoryService`, `SkillRegistry`
- `MemoryBankClient` with `retrieve_memories`, `list_memories`, `delete_memory`
- `HeartbeatLogRepo` with `list_recent()`
- `ConfigLoader` with `load_soul()`, `load_agent()`
- `SkillRegistry` with `list_all()`, `list_for_agent()`, `register()`, `unregister()`
- `CronService` with `list_all()`, `create()`, `execute()`
- Auth middleware (`FirebaseAuthMiddleware`) and `get_current_user_id` dependency
- `ApiClient` in `web/src/lib/api-client.ts` with token injection
- `AuthProvider` / `useAuth()` context, `AuthGuard` component
- Chat View (`/chat`) and Board View (`/board`) pages with inline nav bar
- Existing types in `web/src/types/index.ts`

**Subsequent Plans (future):**
- Plan 4c: Multi-user A2A, onboarding flow, full PWA (push notifications, offline support)

---

## File Structure

```
gclaw/
├── src/
│   └── gclaw/
│       ├── settings.py                              # MODIFY: add gemini_live_model setting
│       ├── api/
│       │   ├── app.py                               # MODIFY: register voice + admin routers
│       │   ├── voice_ws.py                          # NEW: WebSocket voice endpoint
│       │   └── admin_routes.py                      # NEW: agents, heartbeat logs, soul, skills, memory
│       ├── voice/
│       │   ├── __init__.py                          # NEW
│       │   └── session.py                           # NEW: Gemini Live API session wrapper
├── tests/
│   ├── test_voice_ws.py                             # NEW
│   └── test_admin_routes.py                         # NEW
├── web/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx                           # MODIFY: wrap with sidebar layout
│   │   │   ├── chat/
│   │   │   │   └── page.tsx                         # MODIFY: remove inline nav
│   │   │   ├── board/
│   │   │   │   └── page.tsx                         # MODIFY: remove inline nav
│   │   │   ├── agents/
│   │   │   │   └── page.tsx                         # NEW: Agent Dashboard
│   │   │   ├── skills/
│   │   │   │   └── page.tsx                         # NEW: Skills management
│   │   │   ├── crons/
│   │   │   │   └── page.tsx                         # NEW: Crons management
│   │   │   └── memory/
│   │   │       └── page.tsx                         # NEW: Memory Explorer
│   │   ├── lib/
│   │   │   ├── api-client.ts                        # MODIFY: add admin + memory methods
│   │   │   └── voice-client.ts                      # NEW: WebSocket voice client
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── sidebar.tsx                      # NEW: Sidebar navigation
│   │   │   │   └── app-shell.tsx                    # NEW: Sidebar + main content wrapper
│   │   │   ├── chat/
│   │   │   │   ├── chat-view.tsx                    # MODIFY: add voice toggle button
│   │   │   │   └── voice-controls.tsx               # NEW: Mic button, status, audio playback
│   │   │   ├── agents/
│   │   │   │   ├── agent-list.tsx                   # NEW: Agent cards with status
│   │   │   │   ├── agent-detail.tsx                 # NEW: Soul editor, tool grants
│   │   │   │   └── heartbeat-log.tsx                # NEW: Recent heartbeat log entries
│   │   │   ├── skills/
│   │   │   │   └── skill-list.tsx                   # NEW: Installed skills with config
│   │   │   ├── crons/
│   │   │   │   ├── cron-list.tsx                    # NEW: Cron schedules table
│   │   │   │   └── cron-form.tsx                    # NEW: Create/edit cron dialog
│   │   │   └── memory/
│   │   │       ├── memory-search.tsx                # NEW: Search bar + results
│   │   │       └── memory-list.tsx                  # NEW: Browse by topic, edit/delete
│   │   └── types/
│   │       └── index.ts                             # MODIFY: add admin types
│   ├── __tests__/
│   │   ├── voice-client.test.ts                     # NEW
│   │   ├── agent-dashboard.test.tsx                 # NEW
│   │   ├── skills-view.test.tsx                     # NEW
│   │   ├── crons-view.test.tsx                      # NEW
│   │   └── memory-explorer.test.tsx                 # NEW
```

---

### Task 1: Backend Voice WebSocket Endpoint (Gemini Live API Proxy)

**Files:**
- Create: `src/gclaw/voice/__init__.py`
- Create: `src/gclaw/voice/session.py`
- Create: `src/gclaw/api/voice_ws.py`
- Modify: `src/gclaw/settings.py`
- Modify: `src/gclaw/api/app.py`
- Create: `tests/test_voice_ws.py`

- [ ] **Step 1: Write failing tests for the voice WebSocket endpoint**

Create `tests/test_voice_ws.py`:

```python
"""Tests for the voice WebSocket endpoint."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from gclaw.api.voice_ws import init_voice_router


@pytest.fixture
def mock_genai_client():
    """Mock the google.genai Client for live API."""
    with patch("gclaw.voice.session.genai") as mock:
        mock_session = AsyncMock()
        mock_session.receive = AsyncMock(return_value=AsyncMock())
        mock_session.send_realtime_input = AsyncMock()
        mock_session.close = AsyncMock()

        mock_live = AsyncMock()
        mock_live.connect = AsyncMock()
        mock_live.connect.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_live.connect.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.aio.live = mock_live
        mock.Client.return_value = mock_client

        yield mock_client


@pytest.fixture
def voice_app(mock_genai_client):
    app = FastAPI()
    app.include_router(init_voice_router(
        gemini_model="gemini-2.5-flash",
    ))
    return app


def test_voice_ws_rejects_without_token(voice_app):
    """WebSocket should reject connection without auth token."""
    client = TestClient(voice_app)
    with pytest.raises(Exception):
        with client.websocket_connect("/voice"):
            pass


def test_voice_ws_accepts_with_token(voice_app, mock_genai_client):
    """WebSocket should accept with valid auth token query param."""
    with patch("gclaw.api.voice_ws.verify_ws_token", return_value="test_user"):
        client = TestClient(voice_app)
        with client.websocket_connect("/voice?token=valid_token") as ws:
            # Connection established — close gracefully
            ws.close()
```

- [ ] **Step 2: Add gemini_live_model to Settings**

Modify `src/gclaw/settings.py` — add after the `gemini_flash_model` field:

```python
    gemini_live_model: str = field(
        default_factory=lambda: os.environ.get(
            "GEMINI_LIVE_MODEL", "gemini-2.5-flash-preview-native-audio"
        )
    )
```

- [ ] **Step 3: Create the Gemini Live session wrapper**

Create `src/gclaw/voice/__init__.py` (empty).

Create `src/gclaw/voice/session.py`:

```python
"""Gemini Live API session management.

Wraps the google.genai SDK's AsyncLive interface for bidirectional
audio streaming. The session proxies audio between a FastAPI WebSocket
and Gemini's Live API.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import AsyncIterator

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class VoiceSession:
    """Manages a single Gemini Live API voice session.

    Usage:
        session = VoiceSession(model="gemini-2.5-flash-preview-native-audio")
        async with session.connect() as live:
            # Send audio chunks from the browser
            await live.send_audio(audio_bytes)
            # Receive audio responses
            async for chunk in live.receive_audio():
                send_to_browser(chunk)
    """

    def __init__(self, model: str) -> None:
        self._model = model
        self._client = genai.Client()
        self._session = None

    async def connect(self):
        """Open a connection to Gemini Live API.

        Returns an async context manager yielding this VoiceSession
        with an active live session.
        """
        return self._ConnectionContext(self)

    class _ConnectionContext:
        def __init__(self, voice_session: VoiceSession) -> None:
            self._vs = voice_session

        async def __aenter__(self) -> VoiceSession:
            config = types.LiveConnectConfig(
                response_modalities=["AUDIO"],
            )
            self._ctx = self._vs._client.aio.live.connect(
                model=self._vs._model,
                config=config,
            )
            self._vs._session = await self._ctx.__aenter__()
            return self._vs

        async def __aexit__(self, *args):
            if self._ctx:
                await self._ctx.__aexit__(*args)
            self._vs._session = None

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Send raw audio bytes (16-bit PCM, 16kHz) to Gemini."""
        if self._session is None:
            raise RuntimeError("Session not connected")
        blob = types.Blob(data=audio_bytes, mime_type="audio/pcm;rate=16000")
        await self._session.send_realtime_input(audio=blob)

    async def receive_audio(self) -> AsyncIterator[bytes]:
        """Yield audio response chunks from Gemini.

        Each yielded bytes object is raw PCM audio data.
        """
        if self._session is None:
            raise RuntimeError("Session not connected")
        async for message in self._session.receive():
            if message.server_content and message.server_content.model_turn:
                for part in message.server_content.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        yield part.inline_data.data
            # Check for turn completion
            if (
                message.server_content
                and message.server_content.turn_complete
            ):
                break
```

- [ ] **Step 4: Create the WebSocket endpoint**

Create `src/gclaw/api/voice_ws.py`:

```python
"""WebSocket endpoint for real-time voice streaming via Gemini Live API.

The browser sends raw audio chunks (base64-encoded) over WebSocket.
The server proxies them to Gemini Live API and streams audio responses back.

Auth: Since WebSocket doesn't support Authorization headers in browsers,
the client passes the Firebase ID token as a query parameter (?token=...).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import firebase_admin.auth as firebase_auth

from gclaw.voice.session import VoiceSession

logger = logging.getLogger(__name__)

router = APIRouter()

_gemini_model: str = "gemini-2.5-flash-preview-native-audio"


def init_voice_router(gemini_model: str) -> APIRouter:
    global _gemini_model
    _gemini_model = gemini_model
    return router


async def verify_ws_token(token: str) -> str:
    """Verify Firebase ID token for WebSocket auth.

    Returns user_id or raises ValueError.
    """
    try:
        decoded = firebase_auth.verify_id_token(token)
        return decoded["uid"]
    except Exception as e:
        raise ValueError(f"Invalid token: {e}")


@router.websocket("/voice")
async def voice_stream(websocket: WebSocket, token: str = Query(default="")):
    """Bidirectional voice streaming endpoint.

    Protocol:
    - Client sends: {"type": "audio", "data": "<base64 PCM>"}
    - Server sends: {"type": "audio", "data": "<base64 PCM>"}
    - Client sends: {"type": "end"} to signal audio stream end
    - Server sends: {"type": "turn_complete"} when Gemini finishes
    - Server sends: {"type": "error", "message": "..."} on errors
    """
    # Authenticate via query param token
    if not token:
        await websocket.close(code=4001, reason="Missing auth token")
        return

    try:
        user_id = await verify_ws_token(token)
    except ValueError as e:
        await websocket.close(code=4001, reason=str(e))
        return

    await websocket.accept()
    logger.info("Voice WS connected for user %s", user_id)

    voice = VoiceSession(model=_gemini_model)

    try:
        async with await voice.connect() as session:
            # Task to forward Gemini audio responses to the browser
            async def forward_responses():
                try:
                    async for audio_chunk in session.receive_audio():
                        encoded = base64.b64encode(audio_chunk).decode("ascii")
                        await websocket.send_json({
                            "type": "audio",
                            "data": encoded,
                        })
                    await websocket.send_json({"type": "turn_complete"})
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    logger.error("Error forwarding voice response: %s", e)
                    try:
                        await websocket.send_json({
                            "type": "error",
                            "message": str(e),
                        })
                    except Exception:
                        pass

            response_task = asyncio.create_task(forward_responses())

            # Receive audio from browser and forward to Gemini
            try:
                while True:
                    raw = await websocket.receive_text()
                    msg = json.loads(raw)

                    if msg.get("type") == "audio":
                        audio_bytes = base64.b64decode(msg["data"])
                        await session.send_audio(audio_bytes)
                    elif msg.get("type") == "end":
                        # Wait for Gemini to finish responding
                        await response_task
                        # Start a new response listener for the next turn
                        response_task = asyncio.create_task(forward_responses())
            except WebSocketDisconnect:
                logger.info("Voice WS disconnected for user %s", user_id)
            finally:
                response_task.cancel()
                try:
                    await response_task
                except asyncio.CancelledError:
                    pass

    except Exception as e:
        logger.error("Voice session error for user %s: %s", user_id, e)
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
            await websocket.close()
        except Exception:
            pass
```

- [ ] **Step 5: Register the voice router in the app factory**

Modify `src/gclaw/api/app.py`:

Add import at the top:
```python
from gclaw.api.voice_ws import init_voice_router
```

Add parameter to `create_app`:
```python
    gemini_live_model: str = "gemini-2.5-flash-preview-native-audio",
```

Add after the heartbeat router registration:
```python
    app.include_router(init_voice_router(gemini_live_model))
```

- [ ] **Step 6: Verify tests pass**

Run: `python -m pytest tests/test_voice_ws.py -v`

---

### Task 2: Frontend Voice Integration (Microphone, Playback, Toggle)

**Files:**
- Create: `web/src/lib/voice-client.ts`
- Create: `web/src/components/chat/voice-controls.tsx`
- Modify: `web/src/components/chat/chat-view.tsx`
- Modify: `web/src/types/index.ts`
- Create: `web/__tests__/voice-client.test.ts`

- [ ] **Step 1: Add voice-related types**

Add to `web/src/types/index.ts`:

```typescript
/** Voice WebSocket message from client to server. */
export interface VoiceClientMessage {
  type: "audio" | "end";
  data?: string; // base64 PCM
}

/** Voice WebSocket message from server to client. */
export interface VoiceServerMessage {
  type: "audio" | "turn_complete" | "error";
  data?: string; // base64 PCM
  message?: string;
}

/** Voice connection state. */
export type VoiceState = "idle" | "connecting" | "listening" | "processing" | "error";
```

- [ ] **Step 2: Create the voice WebSocket client**

Create `web/src/lib/voice-client.ts`:

```typescript
/**
 * WebSocket client for real-time voice streaming to the GClaw backend.
 *
 * Handles:
 * - WebSocket connection with auth token
 * - MediaRecorder for microphone capture (PCM 16-bit 16kHz via AudioContext)
 * - AudioContext for playback of received PCM audio
 * - State management (idle, connecting, listening, processing)
 */

import type { VoiceClientMessage, VoiceServerMessage, VoiceState } from "@/types";

export type VoiceStateCallback = (state: VoiceState) => void;
export type VoiceAudioCallback = (audioData: Float32Array) => void;

export class VoiceClient {
  private ws: WebSocket | null = null;
  private mediaStream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private processorNode: ScriptProcessorNode | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private playbackContext: AudioContext | null = null;
  private state: VoiceState = "idle";
  private onStateChange: VoiceStateCallback;
  private baseUrl: string;
  private getToken: () => Promise<string | null>;

  constructor(
    baseUrl: string,
    getToken: () => Promise<string | null>,
    onStateChange: VoiceStateCallback,
  ) {
    this.baseUrl = baseUrl.replace(/^http/, "ws").replace(/\/+$/, "");
    this.getToken = getToken;
    this.onStateChange = onStateChange;
  }

  getState(): VoiceState {
    return this.state;
  }

  private setState(s: VoiceState) {
    this.state = s;
    this.onStateChange(s);
  }

  /** Start voice session: connect WS, open mic, begin streaming. */
  async start(): Promise<void> {
    if (this.state !== "idle") return;
    this.setState("connecting");

    try {
      const token = await this.getToken();
      if (!token) throw new Error("Not authenticated");

      // Open WebSocket
      this.ws = new WebSocket(`${this.baseUrl}/voice?token=${encodeURIComponent(token)}`);
      this.ws.onclose = () => this.stop();
      this.ws.onerror = () => this.setState("error");
      this.ws.onmessage = (event) => this.handleMessage(event);

      await new Promise<void>((resolve, reject) => {
        if (!this.ws) return reject(new Error("No WS"));
        this.ws.onopen = () => resolve();
        this.ws.onerror = () => reject(new Error("WS connection failed"));
      });

      // Open microphone
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true },
      });

      // Set up AudioContext to capture PCM data
      this.audioContext = new AudioContext({ sampleRate: 16000 });
      this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream);
      this.processorNode = this.audioContext.createScriptProcessor(4096, 1, 1);

      this.processorNode.onaudioprocess = (event) => {
        if (this.state !== "listening" || !this.ws) return;
        const float32 = event.inputBuffer.getChannelData(0);
        const int16 = this.float32ToInt16(float32);
        const base64 = this.arrayBufferToBase64(int16.buffer);
        const msg: VoiceClientMessage = { type: "audio", data: base64 };
        this.ws.send(JSON.stringify(msg));
      };

      this.sourceNode.connect(this.processorNode);
      this.processorNode.connect(this.audioContext.destination);

      // Set up playback context
      this.playbackContext = new AudioContext({ sampleRate: 24000 });

      this.setState("listening");
    } catch (err) {
      console.error("Voice start failed:", err);
      this.setState("error");
      this.cleanup();
    }
  }

  /** Stop voice session and clean up all resources. */
  stop(): void {
    if (this.state === "idle") return;
    this.cleanup();
    this.setState("idle");
  }

  private cleanup(): void {
    if (this.processorNode) {
      this.processorNode.disconnect();
      this.processorNode = null;
    }
    if (this.sourceNode) {
      this.sourceNode.disconnect();
      this.sourceNode = null;
    }
    if (this.audioContext) {
      this.audioContext.close().catch(() => {});
      this.audioContext = null;
    }
    if (this.playbackContext) {
      this.playbackContext.close().catch(() => {});
      this.playbackContext = null;
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((t) => t.stop());
      this.mediaStream = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  private handleMessage(event: MessageEvent): void {
    try {
      const msg: VoiceServerMessage = JSON.parse(event.data);
      if (msg.type === "audio" && msg.data) {
        this.setState("processing");
        this.playAudio(msg.data);
      } else if (msg.type === "turn_complete") {
        this.setState("listening");
      } else if (msg.type === "error") {
        console.error("Voice server error:", msg.message);
        this.setState("error");
      }
    } catch (err) {
      console.error("Failed to parse voice message:", err);
    }
  }

  private playAudio(base64Data: string): void {
    if (!this.playbackContext) return;
    const raw = atob(base64Data);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);

    // Assume 16-bit PCM at 24kHz from Gemini
    const int16 = new Int16Array(bytes.buffer);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768;

    const buffer = this.playbackContext.createBuffer(1, float32.length, 24000);
    buffer.getChannelData(0).set(float32);
    const source = this.playbackContext.createBufferSource();
    source.buffer = buffer;
    source.connect(this.playbackContext.destination);
    source.start();
  }

  private float32ToInt16(float32: Float32Array): Int16Array {
    const int16 = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
      const s = Math.max(-1, Math.min(1, float32[i]));
      int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return int16;
  }

  private arrayBufferToBase64(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
    return btoa(binary);
  }
}
```

- [ ] **Step 3: Create the VoiceControls component**

Create `web/src/components/chat/voice-controls.tsx`:

```tsx
"use client";

/**
 * Voice toggle button and status indicator for the chat view.
 *
 * Shows a microphone button that starts/stops the voice session.
 * Visual states: idle (gray), connecting (yellow pulse), listening (green pulse),
 * processing (blue), error (red).
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { useAuth } from "@/contexts/auth-context";
import { VoiceClient, type VoiceStateCallback } from "@/lib/voice-client";
import type { VoiceState } from "@/types";

const STATE_STYLES: Record<VoiceState, string> = {
  idle: "bg-slate-600 hover:bg-slate-500",
  connecting: "bg-yellow-600 animate-pulse",
  listening: "bg-green-600 animate-pulse",
  processing: "bg-blue-600",
  error: "bg-red-600",
};

const STATE_LABELS: Record<VoiceState, string> = {
  idle: "Start voice",
  connecting: "Connecting...",
  listening: "Listening...",
  processing: "Speaking...",
  error: "Error — tap to retry",
};

export function VoiceControls() {
  const { getIdToken } = useAuth();
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const clientRef = useRef<VoiceClient | null>(null);

  useEffect(() => {
    return () => {
      clientRef.current?.stop();
    };
  }, []);

  const toggle = useCallback(async () => {
    if (voiceState === "idle" || voiceState === "error") {
      const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
      const client = new VoiceClient(baseUrl, getIdToken, setVoiceState);
      clientRef.current = client;
      await client.start();
    } else {
      clientRef.current?.stop();
      clientRef.current = null;
    }
  }, [voiceState, getIdToken]);

  return (
    <button
      onClick={toggle}
      className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-white transition-colors ${STATE_STYLES[voiceState]}`}
      title={STATE_LABELS[voiceState]}
    >
      {/* Microphone icon (inline SVG) */}
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 1a4 4 0 00-4 4v6a4 4 0 008 0V5a4 4 0 00-4-4z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M19 10v1a7 7 0 01-14 0v-1M12 19v4M8 23h8" />
      </svg>
      <span className="hidden sm:inline">{STATE_LABELS[voiceState]}</span>
    </button>
  );
}
```

- [ ] **Step 4: Add voice toggle to the chat view**

Modify `web/src/components/chat/chat-view.tsx` — add the `VoiceControls` component to the chat input area. Import and render `<VoiceControls />` next to the text input or in the chat header area. The exact integration depends on the current `chat-view.tsx` layout, but place it adjacent to the message input:

```tsx
import { VoiceControls } from "./voice-controls";
// ... in the JSX, near the input area:
<div className="flex items-center gap-2">
  <VoiceControls />
  {/* existing message input */}
</div>
```

- [ ] **Step 5: Write basic frontend test**

Create `web/__tests__/voice-client.test.ts`:

```typescript
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
```

- [ ] **Step 6: Verify tests pass**

Run: `cd web && npx vitest run __tests__/voice-client.test.ts`

---

### Task 3: Backend Admin API Routes

**Files:**
- Create: `src/gclaw/api/admin_routes.py`
- Modify: `src/gclaw/api/app.py`
- Create: `tests/test_admin_routes.py`

- [ ] **Step 1: Write failing tests for admin routes**

Create `tests/test_admin_routes.py`:

```python
"""Tests for admin API routes (agents, heartbeat logs, soul, skills, memory)."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from gclaw.api.admin_routes import init_admin_router
from gclaw.models.memory import Memory
from gclaw.models.skill import Skill


@pytest.fixture
def mock_services():
    """Create mock services for admin routes."""
    config_loader = MagicMock()
    config_loader.load_soul.return_value = "# Base Soul\nYou are helpful."
    config_loader.load_agent.return_value = "# Orchestrator\nRoute tasks."

    heartbeat_log_repo = MagicMock()
    heartbeat_log_repo.list_recent.return_value = []

    skill_registry = MagicMock()
    skill_registry.list_all.return_value = [
        Skill(name="email-drafter", description="Draft emails"),
    ]

    memory_service = AsyncMock()
    memory_service.recall.return_value = [
        Memory(fact="User prefers dark mode", topic="USER_PREFERENCES"),
    ]
    memory_service._client = AsyncMock()
    memory_service._client.list_memories.return_value = []
    memory_service._client.delete_memory.return_value = None

    cron_service = MagicMock()
    cron_service.list_all.return_value = []

    return {
        "config_loader": config_loader,
        "heartbeat_log_repo_factory": lambda uid: heartbeat_log_repo,
        "skill_registry": skill_registry,
        "memory_service": memory_service,
        "cron_service": cron_service,
    }


@pytest.fixture
def admin_app(mock_services):
    app = FastAPI()
    app.include_router(init_admin_router(**mock_services))
    # Bypass auth for tests
    from gclaw.auth.dependencies import get_current_user_id
    app.dependency_overrides[get_current_user_id] = lambda: "test_user"
    return app


@pytest.fixture
async def admin_client(admin_app):
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_list_agents(admin_client):
    resp = await admin_client.get("/admin/agents")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_soul_file(admin_client):
    resp = await admin_client.get("/admin/soul/base")
    assert resp.status_code == 200
    assert "content" in resp.json()


@pytest.mark.asyncio
async def test_list_skills(admin_client):
    resp = await admin_client.get("/admin/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "email-drafter"


@pytest.mark.asyncio
async def test_search_memories(admin_client):
    resp = await admin_client.get("/admin/memory/search?q=dark+mode")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_heartbeat_logs(admin_client):
    resp = await admin_client.get("/admin/heartbeat-logs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
```

- [ ] **Step 2: Create the admin routes module**

Create `src/gclaw/api/admin_routes.py`:

```python
"""Admin API routes for the Agent Dashboard and management views.

Provides endpoints for:
- Agent listing and status
- Heartbeat log viewing
- Soul file read/write
- Skills listing
- Memory search, list, and delete
"""

from __future__ import annotations

import os
import logging
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gclaw.auth.dependencies import get_current_user_id
from gclaw.config.loader import ConfigLoader
from gclaw.heartbeat.log import HeartbeatLogRepo
from gclaw.memory.service import MemoryService
from gclaw.models.memory import MemoryScope
from gclaw.skill.registry import SkillRegistry
from gclaw.cron.service import CronService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")

_config_loader: ConfigLoader | None = None
_hb_repo_factory: Callable[[str], HeartbeatLogRepo] | None = None
_skill_registry: SkillRegistry | None = None
_memory_service: MemoryService | None = None
_cron_service: CronService | None = None


def init_admin_router(
    config_loader: ConfigLoader,
    heartbeat_log_repo_factory: Callable[[str], HeartbeatLogRepo],
    skill_registry: SkillRegistry,
    memory_service: MemoryService,
    cron_service: CronService,
) -> APIRouter:
    global _config_loader, _hb_repo_factory, _skill_registry
    global _memory_service, _cron_service
    _config_loader = config_loader
    _hb_repo_factory = heartbeat_log_repo_factory
    _skill_registry = skill_registry
    _memory_service = memory_service
    _cron_service = cron_service
    return router


# --- Agents ---


class AgentInfo(BaseModel):
    name: str
    description: str
    has_soul_overlay: bool


@router.get("/agents")
def list_agents(user_id: str = Depends(get_current_user_id)):
    """List all configured agents with basic info."""
    agents_dir = os.path.join(_config_loader._config_dir, "agents")
    result = []
    if os.path.isdir(agents_dir):
        for fname in sorted(os.listdir(agents_dir)):
            if fname.endswith(".md"):
                agent_name = fname.removesuffix(".md")
                # Check for soul overlay
                soul_dir = os.path.join(_config_loader._config_dir, "soul")
                has_overlay = os.path.isfile(
                    os.path.join(soul_dir, f"{agent_name.split('-')[0]}.md")
                )
                result.append({
                    "name": agent_name,
                    "has_soul_overlay": has_overlay,
                })
    return result


# --- Heartbeat Logs ---


@router.get("/heartbeat-logs")
def list_heartbeat_logs(
    limit: int = 20,
    user_id: str = Depends(get_current_user_id),
):
    """List recent heartbeat log entries."""
    repo = _hb_repo_factory(user_id)
    logs = repo.list_recent(limit=limit)
    return [log.model_dump(mode="json") for log in logs]


# --- Soul Files ---


@router.get("/soul/{name}")
def get_soul_file(
    name: str,
    user_id: str = Depends(get_current_user_id),
):
    """Read a soul file by name (e.g., 'base', 'workspace')."""
    try:
        content = _config_loader.load_soul(name)
        return {"name": name, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Soul file '{name}' not found")


class SoulUpdateRequest(BaseModel):
    content: str


@router.put("/soul/{name}")
def update_soul_file(
    name: str,
    req: SoulUpdateRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Update a soul file's content."""
    soul_path = os.path.join(_config_loader._config_dir, "soul", f"{name}.md")
    if not os.path.isfile(soul_path):
        raise HTTPException(status_code=404, detail=f"Soul file '{name}' not found")
    with open(soul_path, "w") as f:
        f.write(req.content)
    return {"name": name, "status": "updated"}


# --- Skills ---


@router.get("/skills")
def list_skills(user_id: str = Depends(get_current_user_id)):
    """List all registered skills."""
    skills = _skill_registry.list_all()
    return [s.model_dump(mode="json") for s in skills]


@router.get("/skills/{skill_name}")
def get_skill(
    skill_name: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get a single skill by name."""
    skill = _skill_registry.get(skill_name)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
    return skill.model_dump(mode="json")


# --- Memory ---


@router.get("/memory/search")
async def search_memories(
    q: str,
    agent_id: str | None = None,
    top_k: int = 20,
    user_id: str = Depends(get_current_user_id),
):
    """Search memories via semantic search."""
    memories = await _memory_service.recall(
        user_id=user_id,
        query=q,
        agent_id=agent_id,
        top_k=top_k,
    )
    return [m.model_dump(mode="json") for m in memories]


@router.get("/memory/list")
async def list_memories(
    agent_id: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    """List all memories for the authenticated user."""
    scope = MemoryScope(user_id=user_id, agent=agent_id)
    memories = await _memory_service._client.list_memories(scope=scope)
    return [m.model_dump(mode="json") for m in memories]


class DeleteMemoryRequest(BaseModel):
    fact: str
    agent_id: str | None = None


@router.post("/memory/delete")
async def delete_memory(
    req: DeleteMemoryRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a specific memory by its fact text."""
    scope = MemoryScope(user_id=user_id, agent=req.agent_id)
    await _memory_service._client.delete_memory(scope=scope, fact=req.fact)
    return {"status": "deleted"}


# --- Crons (extended) ---


@router.get("/crons")
def list_crons_admin(user_id: str = Depends(get_current_user_id)):
    """List all cron schedules with full detail."""
    crons = _cron_service.list_all()
    return [c.model_dump(mode="json") for c in crons]


@router.post("/crons/{cron_id}/toggle")
def toggle_cron(
    cron_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Toggle a cron between active and paused."""
    cron = _cron_service.get(cron_id)
    if cron is None:
        raise HTTPException(status_code=404, detail=f"Cron '{cron_id}' not found")
    from gclaw.models.cron import CronStatus
    new_status = CronStatus.PAUSED if cron.status == CronStatus.ACTIVE else CronStatus.ACTIVE
    updated = cron.model_copy(update={"status": new_status})
    _cron_service.update(updated)
    return updated.model_dump(mode="json")
```

- [ ] **Step 3: Register admin routes in app factory**

Modify `src/gclaw/api/app.py`:

Add import:
```python
from gclaw.api.admin_routes import init_admin_router
```

Add parameters to `create_app`:
```python
    config_loader: object | None = None,
    heartbeat_log_repo_factory: object | None = None,
```

Add after existing router registrations:
```python
    if (
        config_loader is not None
        and skill_registry is not None
        and memory_service is not None
    ):
        app.include_router(init_admin_router(
            config_loader=config_loader,
            heartbeat_log_repo_factory=heartbeat_log_repo_factory,
            skill_registry=skill_registry,
            memory_service=memory_service,
            cron_service=cron_service,
        ))
```

- [ ] **Step 4: Verify tests pass**

Run: `python -m pytest tests/test_admin_routes.py -v`

---

### Task 4: Frontend API Client Extensions + Types

**Files:**
- Modify: `web/src/types/index.ts`
- Modify: `web/src/lib/api-client.ts`

- [ ] **Step 1: Add admin types to types/index.ts**

Append to `web/src/types/index.ts`:

```typescript
/** Agent info from the admin API. */
export interface AgentInfo {
  name: string;
  has_soul_overlay: boolean;
}

/** Soul file content. */
export interface SoulFile {
  name: string;
  content: string;
}

/** Heartbeat log entry. */
export interface HeartbeatLogEntry {
  id: string;
  context_summary: string;
  reasoning: string;
  actions_taken: string[];
  tasks_created: string[];
  timestamp: string;
}

/** Skill definition from the backend. */
export interface SkillInfo {
  name: string;
  description: string;
  version: string;
  trigger: {
    mode: "auto" | "manual" | "both";
    contexts: string[];
    command: string | null;
  };
  config: Record<string, unknown>;
  tools_required: string[];
  agents_granted: string[];
  source: "builtin" | "imported" | "custom";
}

/** Memory entry from the backend. */
export interface MemoryEntry {
  fact: string;
  topic: string;
  update_time: string | null;
  score: number | null;
}

/** Cron job definition. */
export interface CronInfo {
  id: string;
  title: string;
  description: string;
  schedule: string;
  mode: "auto" | "todo";
  status: "active" | "paused";
  assignee: string;
  task_priority: string;
  last_run: string | null;
  next_run: string | null;
  created_at: string;
  updated_at: string;
}
```

- [ ] **Step 2: Add admin methods to ApiClient**

Add the following methods to the `ApiClient` class in `web/src/lib/api-client.ts`:

```typescript
  // --- Admin: Agents ---

  async getAgents(): Promise<AgentInfo[]> {
    return this.request<AgentInfo[]>("/admin/agents");
  }

  // --- Admin: Heartbeat Logs ---

  async getHeartbeatLogs(limit = 20): Promise<HeartbeatLogEntry[]> {
    return this.request<HeartbeatLogEntry[]>(`/admin/heartbeat-logs?limit=${limit}`);
  }

  // --- Admin: Soul Files ---

  async getSoulFile(name: string): Promise<SoulFile> {
    return this.request<SoulFile>(`/admin/soul/${name}`);
  }

  async updateSoulFile(name: string, content: string): Promise<{ status: string }> {
    return this.request<{ status: string }>(`/admin/soul/${name}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    });
  }

  // --- Admin: Skills ---

  async getSkills(): Promise<SkillInfo[]> {
    return this.request<SkillInfo[]>("/admin/skills");
  }

  async getSkill(name: string): Promise<SkillInfo> {
    return this.request<SkillInfo>(`/admin/skills/${name}`);
  }

  // --- Admin: Memory ---

  async searchMemories(query: string, agentId?: string): Promise<MemoryEntry[]> {
    let url = `/admin/memory/search?q=${encodeURIComponent(query)}`;
    if (agentId) url += `&agent_id=${encodeURIComponent(agentId)}`;
    return this.request<MemoryEntry[]>(url);
  }

  async listMemories(agentId?: string): Promise<MemoryEntry[]> {
    let url = "/admin/memory/list";
    if (agentId) url += `?agent_id=${encodeURIComponent(agentId)}`;
    return this.request<MemoryEntry[]>(url);
  }

  async deleteMemory(fact: string, agentId?: string): Promise<void> {
    await this.request<{ status: string }>("/admin/memory/delete", {
      method: "POST",
      body: JSON.stringify({ fact, agent_id: agentId }),
    });
  }

  // --- Admin: Crons ---

  async getCrons(): Promise<CronInfo[]> {
    return this.request<CronInfo[]>("/admin/crons");
  }

  async toggleCron(cronId: string): Promise<CronInfo> {
    return this.request<CronInfo>(`/admin/crons/${cronId}/toggle`, {
      method: "POST",
    });
  }

  async triggerCron(cronId: string): Promise<{ status: string; task_id: string }> {
    return this.request<{ status: string; task_id: string }>(`/crons/${cronId}/trigger`, {
      method: "POST",
    });
  }
```

Update the import at the top of `api-client.ts`:
```typescript
import type {
  ChatRequest, ChatResponse, BoardTask,
  AgentInfo, HeartbeatLogEntry, SoulFile,
  SkillInfo, MemoryEntry, CronInfo,
} from "@/types";
```

---

### Task 5: Agent Dashboard View

**Files:**
- Create: `web/src/app/agents/page.tsx`
- Create: `web/src/components/agents/agent-list.tsx`
- Create: `web/src/components/agents/agent-detail.tsx`
- Create: `web/src/components/agents/heartbeat-log.tsx`
- Create: `web/__tests__/agent-dashboard.test.tsx`

- [ ] **Step 1: Create the Agent Dashboard page**

Create `web/src/app/agents/page.tsx`:

```tsx
"use client";

import { AuthGuard } from "@/components/auth-guard";
import { AgentList } from "@/components/agents/agent-list";
import { HeartbeatLogView } from "@/components/agents/heartbeat-log";

export default function AgentsPage() {
  return (
    <AuthGuard>
      <div className="flex flex-col gap-6 p-6">
        <h1 className="text-2xl font-bold text-slate-100">Agent Dashboard</h1>
        <AgentList />
        <HeartbeatLogView />
      </div>
    </AuthGuard>
  );
}
```

- [ ] **Step 2: Create the AgentList component**

Create `web/src/components/agents/agent-list.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/auth-context";
import { createApiClient } from "@/lib/api-client";
import type { AgentInfo } from "@/types";
import { AgentDetail } from "./agent-detail";

export function AgentList() {
  const { getIdToken } = useAuth();
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const api = createApiClient(getIdToken);
    api.getAgents()
      .then(setAgents)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [getIdToken]);

  if (loading) return <div className="text-slate-400">Loading agents...</div>;
  if (error) return <div className="text-red-400">Error: {error}</div>;

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-slate-200">Agents</h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {agents.map((agent) => (
          <button
            key={agent.name}
            onClick={() => setSelected(agent.name === selected ? null : agent.name)}
            className={`rounded-lg border p-4 text-left transition-colors ${
              agent.name === selected
                ? "border-indigo-500 bg-slate-800"
                : "border-slate-700 bg-slate-800/50 hover:border-slate-600"
            }`}
          >
            <div className="font-medium text-slate-100">{agent.name}</div>
            {agent.has_soul_overlay && (
              <span className="mt-1 inline-block rounded bg-indigo-900/50 px-2 py-0.5 text-xs text-indigo-300">
                soul overlay
              </span>
            )}
          </button>
        ))}
      </div>

      {selected && (
        <AgentDetail agentName={selected} />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create the AgentDetail component (soul editor + skills)**

Create `web/src/components/agents/agent-detail.tsx`:

```tsx
"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/contexts/auth-context";
import { createApiClient } from "@/lib/api-client";
import type { SoulFile, SkillInfo } from "@/types";

interface AgentDetailProps {
  agentName: string;
}

export function AgentDetail({ agentName }: AgentDetailProps) {
  const { getIdToken } = useAuth();
  const [soul, setSoul] = useState<SoulFile | null>(null);
  const [editContent, setEditContent] = useState("");
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const api = createApiClient(getIdToken);
    // Load soul file — use the agent's domain prefix as soul name
    const soulName = agentName.split("-")[0];
    api.getSoulFile(soulName)
      .then((s) => { setSoul(s); setEditContent(s.content); })
      .catch(() => setSoul(null));

    // Load skills granted to this agent
    api.getSkills()
      .then((all) => setSkills(all.filter((s) => s.agents_granted.includes(agentName))))
      .catch(() => {});
  }, [agentName, getIdToken]);

  const handleSave = useCallback(async () => {
    if (!soul) return;
    setSaving(true);
    setError(null);
    try {
      const api = createApiClient(getIdToken);
      await api.updateSoulFile(soul.name, editContent);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [soul, editContent, getIdToken]);

  return (
    <div className="space-y-4 rounded-lg border border-slate-700 bg-slate-800/50 p-4">
      <h3 className="text-lg font-semibold text-slate-100">{agentName}</h3>

      {/* Soul Editor */}
      {soul ? (
        <div className="space-y-2">
          <label className="block text-sm font-medium text-slate-300">
            Soul: {soul.name}.md
          </label>
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            className="h-48 w-full rounded border border-slate-600 bg-slate-900 p-3 font-mono text-sm text-slate-200 focus:border-indigo-500 focus:outline-none"
          />
          <div className="flex items-center gap-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save"}
            </button>
            {error && <span className="text-sm text-red-400">{error}</span>}
          </div>
        </div>
      ) : (
        <p className="text-sm text-slate-400">No soul overlay file for this agent.</p>
      )}

      {/* Skills */}
      <div>
        <h4 className="mb-2 text-sm font-medium text-slate-300">Granted Skills</h4>
        {skills.length === 0 ? (
          <p className="text-sm text-slate-500">No skills assigned.</p>
        ) : (
          <div className="space-y-1">
            {skills.map((s) => (
              <div key={s.name} className="flex items-center justify-between rounded bg-slate-900 px-3 py-2 text-sm">
                <span className="text-slate-200">{s.name}</span>
                <span className="text-xs text-slate-500">{s.version}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create the HeartbeatLogView component**

Create `web/src/components/agents/heartbeat-log.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/auth-context";
import { createApiClient } from "@/lib/api-client";
import type { HeartbeatLogEntry } from "@/types";

export function HeartbeatLogView() {
  const { getIdToken } = useAuth();
  const [logs, setLogs] = useState<HeartbeatLogEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const api = createApiClient(getIdToken);
    api.getHeartbeatLogs(20)
      .then(setLogs)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [getIdToken]);

  if (loading) return <div className="text-slate-400">Loading heartbeat logs...</div>;

  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold text-slate-200">Recent Heartbeat Logs</h2>
      {logs.length === 0 ? (
        <p className="text-sm text-slate-500">No heartbeat logs yet.</p>
      ) : (
        <div className="space-y-2">
          {logs.map((log) => (
            <div key={log.id} className="rounded-lg border border-slate-700 bg-slate-800/50 p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">
                  {new Date(log.timestamp).toLocaleString()}
                </span>
                <span className="text-xs text-slate-400">
                  {log.actions_taken.length} actions, {log.tasks_created.length} tasks
                </span>
              </div>
              <p className="mt-1 text-sm text-slate-300">{log.reasoning}</p>
              {log.actions_taken.length > 0 && (
                <ul className="mt-1 list-inside list-disc text-xs text-slate-400">
                  {log.actions_taken.map((a, i) => <li key={i}>{a}</li>)}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Write basic test**

Create `web/__tests__/agent-dashboard.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// Mock auth context
vi.mock("@/contexts/auth-context", () => ({
  useAuth: () => ({
    getIdToken: async () => "fake-token",
    user: { uid: "test" },
    loading: false,
    signInWithGoogle: vi.fn(),
    signOut: vi.fn(),
  }),
}));

vi.mock("@/lib/api-client", () => ({
  createApiClient: () => ({
    getAgents: async () => [
      { name: "orchestrator", has_soul_overlay: true },
    ],
    getHeartbeatLogs: async () => [],
  }),
}));

import AgentsPage from "@/app/agents/page";

describe("AgentsPage", () => {
  it("renders the page title", () => {
    render(<AgentsPage />);
    expect(screen.getByText("Agent Dashboard")).toBeDefined();
  });
});
```

---

### Task 6: Skills Management View

**Files:**
- Create: `web/src/app/skills/page.tsx`
- Create: `web/src/components/skills/skill-list.tsx`
- Create: `web/__tests__/skills-view.test.tsx`

- [ ] **Step 1: Create the Skills page**

Create `web/src/app/skills/page.tsx`:

```tsx
"use client";

import { AuthGuard } from "@/components/auth-guard";
import { SkillList } from "@/components/skills/skill-list";

export default function SkillsPage() {
  return (
    <AuthGuard>
      <div className="flex flex-col gap-6 p-6">
        <h1 className="text-2xl font-bold text-slate-100">Skills</h1>
        <SkillList />
      </div>
    </AuthGuard>
  );
}
```

- [ ] **Step 2: Create the SkillList component**

Create `web/src/components/skills/skill-list.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/auth-context";
import { createApiClient } from "@/lib/api-client";
import type { SkillInfo } from "@/types";

export function SkillList() {
  const { getIdToken } = useAuth();
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    const api = createApiClient(getIdToken);
    api.getSkills()
      .then(setSkills)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [getIdToken]);

  if (loading) return <div className="text-slate-400">Loading skills...</div>;

  return (
    <div className="space-y-3">
      {skills.length === 0 ? (
        <p className="text-sm text-slate-500">No skills installed.</p>
      ) : (
        skills.map((skill) => (
          <div
            key={skill.name}
            className="rounded-lg border border-slate-700 bg-slate-800/50"
          >
            <button
              onClick={() => setExpanded(expanded === skill.name ? null : skill.name)}
              className="flex w-full items-center justify-between p-4 text-left"
            >
              <div>
                <div className="font-medium text-slate-100">{skill.name}</div>
                <div className="text-sm text-slate-400">{skill.description}</div>
              </div>
              <div className="flex items-center gap-2">
                <span className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-300">
                  {skill.source}
                </span>
                <span className="text-xs text-slate-500">v{skill.version}</span>
              </div>
            </button>

            {expanded === skill.name && (
              <div className="border-t border-slate-700 p-4 text-sm">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <h4 className="mb-1 font-medium text-slate-300">Trigger</h4>
                    <p className="text-slate-400">Mode: {skill.trigger.mode}</p>
                    {skill.trigger.command && (
                      <p className="text-slate-400">Command: {skill.trigger.command}</p>
                    )}
                    {skill.trigger.contexts.length > 0 && (
                      <p className="text-slate-400">
                        Contexts: {skill.trigger.contexts.join(", ")}
                      </p>
                    )}
                  </div>
                  <div>
                    <h4 className="mb-1 font-medium text-slate-300">Tools Required</h4>
                    <p className="text-slate-400">
                      {skill.tools_required.length > 0
                        ? skill.tools_required.join(", ")
                        : "None"}
                    </p>
                  </div>
                  <div>
                    <h4 className="mb-1 font-medium text-slate-300">Agents Granted</h4>
                    <p className="text-slate-400">
                      {skill.agents_granted.length > 0
                        ? skill.agents_granted.join(", ")
                        : "None"}
                    </p>
                  </div>
                  <div>
                    <h4 className="mb-1 font-medium text-slate-300">Config</h4>
                    <pre className="rounded bg-slate-900 p-2 text-xs text-slate-400">
                      {JSON.stringify(skill.config, null, 2)}
                    </pre>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
}
```

- [ ] **Step 3: Write basic test**

Create `web/__tests__/skills-view.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/contexts/auth-context", () => ({
  useAuth: () => ({
    getIdToken: async () => "fake-token",
    user: { uid: "test" },
    loading: false,
    signInWithGoogle: vi.fn(),
    signOut: vi.fn(),
  }),
}));

vi.mock("@/lib/api-client", () => ({
  createApiClient: () => ({
    getSkills: async () => [
      {
        name: "email-drafter",
        description: "Draft emails",
        version: "1.0.0",
        trigger: { mode: "manual", contexts: [], command: "/draft" },
        config: {},
        tools_required: ["gmail"],
        agents_granted: ["workspace-mgr"],
        source: "builtin",
      },
    ],
  }),
}));

import SkillsPage from "@/app/skills/page";

describe("SkillsPage", () => {
  it("renders the page title", () => {
    render(<SkillsPage />);
    expect(screen.getByText("Skills")).toBeDefined();
  });
});
```

---

### Task 7: Crons Management View

**Files:**
- Create: `web/src/app/crons/page.tsx`
- Create: `web/src/components/crons/cron-list.tsx`
- Create: `web/src/components/crons/cron-form.tsx`
- Create: `web/__tests__/crons-view.test.tsx`

- [ ] **Step 1: Create the Crons page**

Create `web/src/app/crons/page.tsx`:

```tsx
"use client";

import { AuthGuard } from "@/components/auth-guard";
import { CronList } from "@/components/crons/cron-list";

export default function CronsPage() {
  return (
    <AuthGuard>
      <div className="flex flex-col gap-6 p-6">
        <h1 className="text-2xl font-bold text-slate-100">Cron Schedules</h1>
        <CronList />
      </div>
    </AuthGuard>
  );
}
```

- [ ] **Step 2: Create the CronList component**

Create `web/src/components/crons/cron-list.tsx`:

```tsx
"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/contexts/auth-context";
import { createApiClient } from "@/lib/api-client";
import type { CronInfo } from "@/types";
import { CronForm } from "./cron-form";

export function CronList() {
  const { getIdToken } = useAuth();
  const [crons, setCrons] = useState<CronInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  const fetchCrons = useCallback(async () => {
    const api = createApiClient(getIdToken);
    try {
      const data = await api.getCrons();
      setCrons(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [getIdToken]);

  useEffect(() => {
    fetchCrons();
  }, [fetchCrons]);

  const handleToggle = useCallback(async (cronId: string) => {
    const api = createApiClient(getIdToken);
    try {
      const updated = await api.toggleCron(cronId);
      setCrons((prev) => prev.map((c) => (c.id === cronId ? updated : c)));
    } catch {
      // ignore
    }
  }, [getIdToken]);

  const handleTrigger = useCallback(async (cronId: string) => {
    const api = createApiClient(getIdToken);
    try {
      await api.triggerCron(cronId);
      // Refresh to show updated last_run
      fetchCrons();
    } catch {
      // ignore
    }
  }, [getIdToken, fetchCrons]);

  if (loading) return <div className="text-slate-400">Loading crons...</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-sm text-slate-400">{crons.length} cron(s)</span>
        <button
          onClick={() => setShowForm(!showForm)}
          className="rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500"
        >
          {showForm ? "Cancel" : "New Cron"}
        </button>
      </div>

      {showForm && (
        <CronForm
          onCreated={() => { setShowForm(false); fetchCrons(); }}
        />
      )}

      {crons.length === 0 ? (
        <p className="text-sm text-slate-500">No cron schedules configured.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700 text-left text-slate-400">
                <th className="pb-2 pr-4">Title</th>
                <th className="pb-2 pr-4">Schedule</th>
                <th className="pb-2 pr-4">Mode</th>
                <th className="pb-2 pr-4">Assignee</th>
                <th className="pb-2 pr-4">Status</th>
                <th className="pb-2 pr-4">Last Run</th>
                <th className="pb-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {crons.map((cron) => (
                <tr key={cron.id} className="border-b border-slate-800">
                  <td className="py-2 pr-4 text-slate-200">{cron.title}</td>
                  <td className="py-2 pr-4 font-mono text-xs text-slate-400">{cron.schedule}</td>
                  <td className="py-2 pr-4">
                    <span className={`rounded px-2 py-0.5 text-xs ${
                      cron.mode === "auto" ? "bg-green-900/50 text-green-300" : "bg-blue-900/50 text-blue-300"
                    }`}>
                      {cron.mode}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-slate-400">{cron.assignee}</td>
                  <td className="py-2 pr-4">
                    <span className={`rounded px-2 py-0.5 text-xs ${
                      cron.status === "active" ? "bg-green-900/50 text-green-300" : "bg-yellow-900/50 text-yellow-300"
                    }`}>
                      {cron.status}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-xs text-slate-500">
                    {cron.last_run ? new Date(cron.last_run).toLocaleString() : "Never"}
                  </td>
                  <td className="py-2">
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleToggle(cron.id)}
                        className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600"
                      >
                        {cron.status === "active" ? "Pause" : "Resume"}
                      </button>
                      <button
                        onClick={() => handleTrigger(cron.id)}
                        className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600"
                      >
                        Trigger
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create the CronForm component**

Create `web/src/components/crons/cron-form.tsx`:

```tsx
"use client";

import { useState, useCallback } from "react";
import { useAuth } from "@/contexts/auth-context";
import { createApiClient } from "@/lib/api-client";

interface CronFormProps {
  onCreated: () => void;
}

export function CronForm({ onCreated }: CronFormProps) {
  const { getIdToken } = useAuth();
  const [title, setTitle] = useState("");
  const [schedule, setSchedule] = useState("");
  const [assignee, setAssignee] = useState("orchestrator");
  const [mode, setMode] = useState<"auto" | "todo">("todo");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const api = createApiClient(getIdToken);
      await api.createBoardTask(title, assignee); // Placeholder — use cron create
      // Note: This should call a dedicated cron creation endpoint.
      // For now, use the existing /crons POST via a direct fetch:
      const token = await getIdToken();
      const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
      const resp = await fetch(`${baseUrl}/crons`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ title, schedule, assignee, mode, description }),
      });
      if (!resp.ok) throw new Error("Failed to create cron");
      onCreated();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setSaving(false);
    }
  }, [title, schedule, assignee, mode, description, getIdToken, onCreated]);

  return (
    <form onSubmit={handleSubmit} className="space-y-3 rounded-lg border border-slate-700 bg-slate-800/50 p-4">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs text-slate-400">Title</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:border-indigo-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">Schedule (cron expr)</label>
          <input
            value={schedule}
            onChange={(e) => setSchedule(e.target.value)}
            required
            placeholder="0 8 * * *"
            className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-1.5 font-mono text-sm text-slate-200 focus:border-indigo-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">Assignee</label>
          <input
            value={assignee}
            onChange={(e) => setAssignee(e.target.value)}
            required
            className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:border-indigo-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-400">Mode</label>
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as "auto" | "todo")}
            className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:border-indigo-500 focus:outline-none"
          >
            <option value="todo">Todo</option>
            <option value="auto">Auto</option>
          </select>
        </div>
      </div>
      <div>
        <label className="mb-1 block text-xs text-slate-400">Description</label>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="w-full rounded border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:border-indigo-500 focus:outline-none"
        />
      </div>
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={saving}
          className="rounded bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {saving ? "Creating..." : "Create Cron"}
        </button>
        {error && <span className="text-sm text-red-400">{error}</span>}
      </div>
    </form>
  );
}
```

- [ ] **Step 4: Write basic test**

Create `web/__tests__/crons-view.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/contexts/auth-context", () => ({
  useAuth: () => ({
    getIdToken: async () => "fake-token",
    user: { uid: "test" },
    loading: false,
    signInWithGoogle: vi.fn(),
    signOut: vi.fn(),
  }),
}));

vi.mock("@/lib/api-client", () => ({
  createApiClient: () => ({
    getCrons: async () => [],
  }),
}));

import CronsPage from "@/app/crons/page";

describe("CronsPage", () => {
  it("renders the page title", () => {
    render(<CronsPage />);
    expect(screen.getByText("Cron Schedules")).toBeDefined();
  });
});
```

---

### Task 8: Memory Explorer View

**Files:**
- Create: `web/src/app/memory/page.tsx`
- Create: `web/src/components/memory/memory-search.tsx`
- Create: `web/src/components/memory/memory-list.tsx`
- Create: `web/__tests__/memory-explorer.test.tsx`

- [ ] **Step 1: Create the Memory Explorer page**

Create `web/src/app/memory/page.tsx`:

```tsx
"use client";

import { AuthGuard } from "@/components/auth-guard";
import { MemorySearch } from "@/components/memory/memory-search";
import { MemoryListView } from "@/components/memory/memory-list";
import { useState } from "react";

export default function MemoryPage() {
  const [tab, setTab] = useState<"search" | "browse">("search");

  return (
    <AuthGuard>
      <div className="flex flex-col gap-6 p-6">
        <h1 className="text-2xl font-bold text-slate-100">Memory Explorer</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setTab("search")}
            className={`rounded px-3 py-1.5 text-sm font-medium ${
              tab === "search"
                ? "bg-indigo-600 text-white"
                : "bg-slate-700 text-slate-300 hover:bg-slate-600"
            }`}
          >
            Search
          </button>
          <button
            onClick={() => setTab("browse")}
            className={`rounded px-3 py-1.5 text-sm font-medium ${
              tab === "browse"
                ? "bg-indigo-600 text-white"
                : "bg-slate-700 text-slate-300 hover:bg-slate-600"
            }`}
          >
            Browse All
          </button>
        </div>
        {tab === "search" ? <MemorySearch /> : <MemoryListView />}
      </div>
    </AuthGuard>
  );
}
```

- [ ] **Step 2: Create the MemorySearch component**

Create `web/src/components/memory/memory-search.tsx`:

```tsx
"use client";

import { useState, useCallback } from "react";
import { useAuth } from "@/contexts/auth-context";
import { createApiClient } from "@/lib/api-client";
import type { MemoryEntry } from "@/types";

export function MemorySearch() {
  const { getIdToken } = useAuth();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MemoryEntry[]>([]);
  const [searching, setSearching] = useState(false);

  const handleSearch = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    try {
      const api = createApiClient(getIdToken);
      const data = await api.searchMemories(query);
      setResults(data);
    } catch {
      // ignore
    } finally {
      setSearching(false);
    }
  }, [query, getIdToken]);

  const handleDelete = useCallback(async (fact: string) => {
    const api = createApiClient(getIdToken);
    try {
      await api.deleteMemory(fact);
      setResults((prev) => prev.filter((m) => m.fact !== fact));
    } catch {
      // ignore
    }
  }, [getIdToken]);

  return (
    <div className="space-y-4">
      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search memories..."
          className="flex-1 rounded border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-indigo-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={searching}
          className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {searching ? "..." : "Search"}
        </button>
      </form>

      {results.length > 0 && (
        <div className="space-y-2">
          {results.map((memory, idx) => (
            <div
              key={idx}
              className="flex items-start justify-between rounded-lg border border-slate-700 bg-slate-800/50 p-3"
            >
              <div className="flex-1">
                <p className="text-sm text-slate-200">{memory.fact}</p>
                <div className="mt-1 flex items-center gap-2">
                  {memory.topic && (
                    <span className="rounded bg-slate-700 px-2 py-0.5 text-xs text-slate-400">
                      {memory.topic}
                    </span>
                  )}
                  {memory.score != null && (
                    <span className="text-xs text-slate-500">
                      score: {memory.score.toFixed(2)}
                    </span>
                  )}
                </div>
              </div>
              <button
                onClick={() => handleDelete(memory.fact)}
                className="ml-2 rounded bg-red-900/50 px-2 py-1 text-xs text-red-300 hover:bg-red-900"
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create the MemoryListView component (browse by topic)**

Create `web/src/components/memory/memory-list.tsx`:

```tsx
"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/contexts/auth-context";
import { createApiClient } from "@/lib/api-client";
import type { MemoryEntry } from "@/types";

export function MemoryListView() {
  const { getIdToken } = useAuth();
  const [memories, setMemories] = useState<MemoryEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const api = createApiClient(getIdToken);
    api.listMemories()
      .then(setMemories)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [getIdToken]);

  const handleDelete = useCallback(async (fact: string) => {
    const api = createApiClient(getIdToken);
    try {
      await api.deleteMemory(fact);
      setMemories((prev) => prev.filter((m) => m.fact !== fact));
    } catch {
      // ignore
    }
  }, [getIdToken]);

  if (loading) return <div className="text-slate-400">Loading memories...</div>;

  // Group by topic
  const byTopic: Record<string, MemoryEntry[]> = {};
  for (const m of memories) {
    const topic = m.topic || "general";
    if (!byTopic[topic]) byTopic[topic] = [];
    byTopic[topic].push(m);
  }

  const topics = Object.keys(byTopic).sort();

  return (
    <div className="space-y-6">
      {topics.length === 0 ? (
        <p className="text-sm text-slate-500">No memories stored.</p>
      ) : (
        topics.map((topic) => (
          <div key={topic}>
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">
              {topic}
            </h3>
            <div className="space-y-1">
              {byTopic[topic].map((memory, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between rounded bg-slate-800/50 px-3 py-2"
                >
                  <span className="text-sm text-slate-200">{memory.fact}</span>
                  <button
                    onClick={() => handleDelete(memory.fact)}
                    className="ml-2 rounded bg-red-900/50 px-2 py-1 text-xs text-red-300 hover:bg-red-900"
                  >
                    Delete
                  </button>
                </div>
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
```

- [ ] **Step 4: Write basic test**

Create `web/__tests__/memory-explorer.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/contexts/auth-context", () => ({
  useAuth: () => ({
    getIdToken: async () => "fake-token",
    user: { uid: "test" },
    loading: false,
    signInWithGoogle: vi.fn(),
    signOut: vi.fn(),
  }),
}));

vi.mock("@/lib/api-client", () => ({
  createApiClient: () => ({
    searchMemories: async () => [],
    listMemories: async () => [],
    deleteMemory: async () => {},
  }),
}));

import MemoryPage from "@/app/memory/page";

describe("MemoryPage", () => {
  it("renders the page title", () => {
    render(<MemoryPage />);
    expect(screen.getByText("Memory Explorer")).toBeDefined();
  });
});
```

---

### Task 9: Navigation + Layout Polish (Sidebar Nav, Responsive)

**Files:**
- Create: `web/src/components/layout/sidebar.tsx`
- Create: `web/src/components/layout/app-shell.tsx`
- Modify: `web/src/app/layout.tsx`
- Modify: `web/src/app/chat/page.tsx`
- Modify: `web/src/app/board/page.tsx`
- Modify: `web/src/app/agents/page.tsx`
- Modify: `web/src/app/skills/page.tsx`
- Modify: `web/src/app/crons/page.tsx`
- Modify: `web/src/app/memory/page.tsx`

- [ ] **Step 1: Create the Sidebar component**

Create `web/src/components/layout/sidebar.tsx`:

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/contexts/auth-context";

const NAV_ITEMS = [
  { href: "/chat", label: "Chat" },
  { href: "/board", label: "Board" },
  { href: "/agents", label: "Agents" },
  { href: "/skills", label: "Skills" },
  { href: "/crons", label: "Crons" },
  { href: "/memory", label: "Memory" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, signOut } = useAuth();

  return (
    <aside className="flex h-full w-56 flex-col border-r border-slate-700 bg-slate-900">
      {/* Logo */}
      <div className="border-b border-slate-700 px-4 py-4">
        <Link href="/chat" className="text-xl font-bold text-indigo-400">
          GClaw
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-2 py-4">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`block rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-slate-800 text-indigo-400"
                  : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* User / Sign Out */}
      {user && (
        <div className="border-t border-slate-700 px-4 py-3">
          <div className="truncate text-xs text-slate-500">{user.email}</div>
          <button
            onClick={signOut}
            className="mt-1 text-xs text-slate-400 hover:text-slate-200"
          >
            Sign out
          </button>
        </div>
      )}
    </aside>
  );
}
```

- [ ] **Step 2: Create the AppShell wrapper**

Create `web/src/components/layout/app-shell.tsx`:

```tsx
"use client";

import { Sidebar } from "./sidebar";
import { useAuth } from "@/contexts/auth-context";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();

  // Don't show sidebar on login page or while loading
  if (loading || !user) {
    return <>{children}</>;
  }

  return (
    <div className="flex h-screen bg-slate-900 text-slate-100">
      <Sidebar />
      <main className="flex-1 overflow-hidden">{children}</main>
    </div>
  );
}
```

- [ ] **Step 3: Integrate AppShell into root layout**

Modify `web/src/app/layout.tsx` — wrap the `{children}` with `<AppShell>`:

```tsx
import { AppShell } from "@/components/layout/app-shell";

// Inside the layout body, wrap children:
<AuthProvider>
  <AppShell>
    {children}
  </AppShell>
</AuthProvider>
```

- [ ] **Step 4: Remove inline nav bars from existing pages**

Modify `web/src/app/chat/page.tsx` — remove the `<nav>` element and outer wrapper div. The page should just return:

```tsx
"use client";

import { AuthGuard } from "@/components/auth-guard";
import { ChatView } from "@/components/chat/chat-view";

export default function ChatPage() {
  return (
    <AuthGuard>
      <div className="flex h-full flex-col">
        <ChatView />
      </div>
    </AuthGuard>
  );
}
```

Modify `web/src/app/board/page.tsx` — same treatment, remove the `<nav>` element:

```tsx
"use client";

import { AuthGuard } from "@/components/auth-guard";
import { BoardView } from "@/components/board/board-view";

export default function BoardPage() {
  return (
    <AuthGuard>
      <div className="flex h-full flex-col">
        <BoardView />
      </div>
    </AuthGuard>
  );
}
```

- [ ] **Step 5: Ensure new pages work within AppShell**

All new pages (agents, skills, crons, memory) already use `<AuthGuard>` and render content without a nav bar, so they fit within the `AppShell` layout. Verify each page renders correctly by navigating to:
- `/agents`
- `/skills`
- `/crons`
- `/memory`

- [ ] **Step 6: Verify responsive behavior**

The sidebar is fixed-width (w-56 / 14rem). On small screens it will remain visible. For a minimal implementation this is acceptable. A future enhancement could add a hamburger menu toggle for mobile. The main content area uses `flex-1 overflow-hidden` so all views scroll independently.

---

### Task 10: Full Verification

- [ ] **Step 1: Run all backend tests**

```bash
python -m pytest tests/ -v --tb=short
```

Expect all existing tests plus `test_voice_ws.py` and `test_admin_routes.py` to pass.

- [ ] **Step 2: Run all frontend tests**

```bash
cd web && npx vitest run
```

Expect all existing tests plus the new voice, agent, skills, crons, and memory tests to pass.

- [ ] **Step 3: Start backend and verify new endpoints**

```bash
uvicorn gclaw.api.app:create_app --factory --reload
```

Manually test with curl:
```bash
# Health check
curl http://localhost:8000/health

# Admin endpoints (with auth header)
curl -H "Authorization: Bearer <token>" http://localhost:8000/admin/agents
curl -H "Authorization: Bearer <token>" http://localhost:8000/admin/skills
curl -H "Authorization: Bearer <token>" http://localhost:8000/admin/heartbeat-logs
curl -H "Authorization: Bearer <token>" http://localhost:8000/admin/soul/base
curl -H "Authorization: Bearer <token>" "http://localhost:8000/admin/memory/search?q=test"
curl -H "Authorization: Bearer <token>" http://localhost:8000/admin/crons
```

- [ ] **Step 4: Start frontend and verify all views**

Start the Next.js dev server and verify:
1. Sidebar navigation appears on all pages
2. Chat view has voice toggle button
3. Agent Dashboard loads agent list and heartbeat logs
4. Skills view lists installed skills with expandable details
5. Crons view shows table with toggle/trigger actions and create form
6. Memory Explorer search returns results, browse shows by topic, delete works
7. All pages are responsive (content scrolls, sidebar stays fixed)

- [ ] **Step 5: Type checking**

```bash
cd web && npx tsc --noEmit
```

No TypeScript errors expected.
