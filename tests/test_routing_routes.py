"""Tests for model routing admin endpoints."""

import pytest
from fastapi.testclient import TestClient
from gclaw.api.routing_routes import init_routing_router
from gclaw.models.model_config import ModelEndpoint, TaskProfile, RoutingRule
from gclaw.routing.router import ModelRouter


@pytest.fixture
def router():
    endpoints = {
        "gemini-pro": ModelEndpoint(
            name="gemini-pro",
            endpoint_id="gemini-2.5-pro",
            max_context_tokens=1_000_000,
        ),
        "gemma-4": ModelEndpoint(
            name="gemma-4",
            endpoint_id="projects/test/locations/us-central1/endpoints/111",
            max_context_tokens=256_000,
        ),
    }
    rules = [
        RoutingRule(task_profile=TaskProfile.ORCHESTRATION, model_name="gemini-pro"),
        RoutingRule(task_profile=TaskProfile.SUMMARIZATION, model_name="gemma-4"),
    ]
    return ModelRouter(endpoints=endpoints, rules=rules, default_model="gemini-2.5-flash")


@pytest.fixture
def client(router):
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(init_routing_router(router))
    return TestClient(app)


def test_get_routing_status(client):
    resp = client.get("/routing/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert len(data["endpoints"]) == 2
    assert len(data["rules"]) == 2


def test_get_routing_resolve(client):
    resp = client.get("/routing/resolve/orchestration")
    assert resp.status_code == 200
    data = resp.json()
    assert data["profile"] == "orchestration"
    assert data["model_id"] == "gemini-2.5-pro"


def test_get_routing_resolve_agent(client):
    resp = client.get("/routing/resolve-agent/orchestrator")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_name"] == "orchestrator"
    assert data["model_id"] == "gemini-2.5-pro"


def test_routing_disabled():
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(init_routing_router(None))
    client = TestClient(app)
    resp = client.get("/routing/status")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
