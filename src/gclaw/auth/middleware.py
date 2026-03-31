"""Firebase Auth middleware for FastAPI.

Verifies Firebase ID tokens from the Authorization header and injects
the authenticated user_id into request.state for downstream handlers.
"""

from __future__ import annotations

import logging

from firebase_admin import auth as firebase_auth
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Paths that do not require authentication
_PUBLIC_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})


class FirebaseAuthMiddleware(BaseHTTPMiddleware):
    """Verify Firebase ID token on every request (except public paths).

    Expects header: Authorization: Bearer <firebase_id_token>
    Sets: request.state.user_id = decoded token uid
    """

    async def dispatch(self, request: Request, call_next):
        # Skip auth for public endpoints
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        # Extract Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing Authorization header"},
            )

        # Parse Bearer token
        parts = auth_header.split(" ", 1)
        if len(parts) != 2 or parts[0] != "Bearer":
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid Authorization header format. Expected: Bearer <token>"},
            )

        token = parts[1]

        # Verify token with Firebase Admin SDK
        try:
            decoded = firebase_auth.verify_id_token(token)
            request.state.user_id = decoded["uid"]
        except Exception as exc:
            logger.warning("Firebase token verification failed: %s", exc)
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
            )

        return await call_next(request)
