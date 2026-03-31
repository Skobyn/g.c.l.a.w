"""FastAPI dependencies for authentication."""

from __future__ import annotations

from fastapi import HTTPException, Request


async def get_current_user_id(request: Request) -> str:
    """Extract authenticated user_id from request state.

    The FirebaseAuthMiddleware must run before this dependency.
    Returns the user_id string set by the middleware.
    Raises 401 if no user_id is present (middleware was bypassed or failed).
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id
