"""Model router — resolves task profiles to Vertex AI model endpoints.

Returns ADK-ready model references: a string (Gemini/Vertex) or a LiteLlm
instance (OpenRouter and other OpenAI-compatible providers) so ADK's native
Runner can execute agents uniformly regardless of provider.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Union

from gclaw.models.model_config import ModelEndpoint, RoutingRule, TaskProfile

if TYPE_CHECKING:
    from google.adk.models.lite_llm import LiteLlm

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

AdkModel = Union[str, "LiteLlm"]


def _endpoint_to_adk_model(
    endpoint: ModelEndpoint | None, default: str
) -> AdkModel:
    """Convert a ModelEndpoint to an ADK-ready model reference."""
    if endpoint is None:
        return default

    if endpoint.provider in ("gemini", "vertex"):
        return endpoint.endpoint_id

    from google.adk.models.lite_llm import LiteLlm

    prefixed = endpoint.endpoint_id
    if endpoint.provider == "openrouter" and not prefixed.startswith("openrouter/"):
        prefixed = f"openrouter/{prefixed}"

    return LiteLlm(model=prefixed)


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
        """Resolve a task profile to a bare model ID string (legacy)."""
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
        """Resolve an agent name to a bare model ID string (legacy)."""
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

    def build_adk_model_for_profile(self, profile: TaskProfile) -> AdkModel:
        """Return an ADK-ready model for a task profile.

        Gemini/Vertex providers return a bare string model ID.
        Other providers return a LiteLlm instance ADK's native Runner can execute.
        """
        endpoint = self.get_endpoint(profile)
        return _endpoint_to_adk_model(endpoint, self._default)

    def build_adk_model_for_agent(self, agent_name: str) -> AdkModel:
        """Return an ADK-ready model for a named agent.

        Uses AGENT_PROFILE_MAP, falling back to SPECIALIST_SUFFIX_MAP matching.
        """
        profile = AGENT_PROFILE_MAP.get(agent_name)
        if profile is None:
            for suffix, prof in SPECIALIST_SUFFIX_MAP.items():
                if suffix in agent_name:
                    profile = prof
                    break
        if profile is None:
            return self._default
        return self.build_adk_model_for_profile(profile)
