"""Model router — resolves task profiles to Vertex AI model endpoints."""

from __future__ import annotations

import logging

from gclaw.models.model_config import ModelEndpoint, RoutingRule, TaskProfile

logger = logging.getLogger(__name__)

AGENT_PROFILE_MAP: dict[str, TaskProfile] = {
    "orchestrator": TaskProfile.ORCHESTRATION,
    "workspace-mgr": TaskProfile.SUMMARIZATION,
    "dev-mgr": TaskProfile.CODE_GENERATION,
    "home-mgr": TaskProfile.SUMMARIZATION,
    "comms-mgr": TaskProfile.PERSONALITY,
    "research-mgr": TaskProfile.SUMMARIZATION,
}

SPECIALIST_SUFFIX_MAP: dict[str, TaskProfile] = {
    "code": TaskProfile.CODE_GENERATION,
    "search": TaskProfile.TOOL_EXECUTION,
    "draft": TaskProfile.PERSONALITY,
    "summarize": TaskProfile.SUMMARIZATION,
    "audit": TaskProfile.TOOL_EXECUTION,
}


class ModelRouter:
    """Resolves task profiles to model endpoint IDs for ADK agents."""

    def __init__(
        self,
        endpoints: dict[str, ModelEndpoint],
        rules: list[RoutingRule],
        default_model: str,
    ) -> None:
        self._endpoints = endpoints
        self._rules = {r.task_profile: r.model_name for r in rules}
        self._default = default_model

    def resolve(self, profile: TaskProfile) -> str:
        model_name = self._rules.get(profile)
        if model_name is None:
            return self._default

        endpoint = self._endpoints.get(model_name)
        if endpoint is None:
            logger.warning(
                "No endpoint registered for model %s, using default", model_name
            )
            return self._default

        return endpoint.endpoint_id

    def resolve_for_agent(self, agent_name: str) -> str:
        profile = AGENT_PROFILE_MAP.get(agent_name)
        if profile is not None:
            return self.resolve(profile)

        for suffix, prof in SPECIALIST_SUFFIX_MAP.items():
            if suffix in agent_name:
                return self.resolve(prof)

        return self._default

    def get_endpoint(self, profile: TaskProfile) -> ModelEndpoint | None:
        model_name = self._rules.get(profile)
        if model_name is None:
            return None
        return self._endpoints.get(model_name)
