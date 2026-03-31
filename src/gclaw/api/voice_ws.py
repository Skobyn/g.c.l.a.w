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
