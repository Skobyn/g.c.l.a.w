"""Gemini Live API session management.

Wraps the google.genai SDK's AsyncLive interface for bidirectional
audio streaming. The session proxies audio between a FastAPI WebSocket
and Gemini's Live API.
"""

from __future__ import annotations

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
            self._ctx = None

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
