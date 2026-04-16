"""Tests for GET /chat/history."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gclaw.api.chat import init_chat_router
from gclaw.dispatch.runner_registry import AgentRunnerRegistry
from gclaw.models.session import MessageRole, SessionMessage


def _mock_runner():
    r = MagicMock()
    r.run = MagicMock()
    r.end_session = MagicMock()
    return r


def _app_with(session_store=None, *, default_agent="orchestrator"):
    reg = AgentRunnerRegistry(
        default_agent=default_agent,
        builder=lambda _name: _mock_runner(),
    )
    reg.register(default_agent, _mock_runner())
    router = init_chat_router(reg, session_store=session_store)
    app = FastAPI()
    app.include_router(router)

    # Dev auth bypass — inject a user_id via middleware.
    @app.middleware("http")
    async def _inject_user(request, call_next):
        request.state.user_id = "u1"
        return await call_next(request)

    return app


def test_history_no_session_store_returns_empty():
    app = _app_with(session_store=None)
    c = TestClient(app)
    r = c.get("/chat/history", params={"session_id": "sess_1"})
    assert r.status_code == 200
    body = r.json()
    assert body["messages"] == []
    assert body["agent_name"] == "orchestrator"
    assert body["session_id"] == "sess_1"


def test_history_returns_persisted_messages():
    ts = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
    msgs = [
        SessionMessage(role=MessageRole.USER, content="hi", timestamp=ts),
        SessionMessage(
            role=MessageRole.AGENT, content="hello", timestamp=ts
        ),
    ]
    store = MagicMock()
    store.get_history = MagicMock(return_value=msgs)

    app = _app_with(session_store=store)
    c = TestClient(app)
    r = c.get("/chat/history", params={"session_id": "sess_1"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["messages"]) == 2
    assert body["messages"][0] == {
        "role": "user",
        "content": "hi",
        "timestamp": ts.isoformat(),
    }
    # MessageRole.AGENT is translated to the canonical "assistant" role
    # so the UI doesn't need to know about the backend's internal naming.
    assert body["messages"][1]["role"] == "assistant"
    # Scoped to the default (orchestrator) — raw session_id is passed through
    store.get_history.assert_called_once()
    kwargs = store.get_history.call_args.kwargs
    assert kwargs["session_id"] == "sess_1"
    assert kwargs["user_id"] == "u1"


def test_history_scoped_session_id_for_non_default_agent():
    store = MagicMock()
    store.get_history = MagicMock(return_value=[])

    app = _app_with(session_store=store)
    c = TestClient(app)
    r = c.get(
        "/chat/history",
        params={"session_id": "sess_1", "agent_name": "intel"},
    )
    assert r.status_code == 200
    kwargs = store.get_history.call_args.kwargs
    # Non-default agent: session id gets the "::agent" suffix
    assert kwargs["session_id"] == "sess_1::intel"


def test_history_missing_session_returns_empty_not_404():
    store = MagicMock()
    # SessionService.get_history raises ValueError when session absent
    store.get_history = MagicMock(side_effect=ValueError("not found"))

    app = _app_with(session_store=store)
    c = TestClient(app)
    r = c.get("/chat/history", params={"session_id": "never_existed"})
    assert r.status_code == 200
    assert r.json()["messages"] == []


def test_history_respects_limit():
    store = MagicMock()
    store.get_history = MagicMock(return_value=[])

    app = _app_with(session_store=store)
    c = TestClient(app)
    c.get(
        "/chat/history",
        params={"session_id": "sess_1", "limit": "25"},
    )
    kwargs = store.get_history.call_args.kwargs
    assert kwargs["limit"] == 25
