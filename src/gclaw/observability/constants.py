"""Shared constants for observability — OpenInference attribute keys.

Mirrors the subset of the OpenInference semantic conventions we populate
today, so span-emitting sites don't need to import the upstream enum (and
so tests can assert attributes against a stable surface).
"""

# Service identity
SERVICE_NAME = "service.name"
SERVICE_VERSION = "service.version"

# Session / user
SESSION_ID = "session.id"
USER_ID = "user.id"

# Agent graph (orchestrator -> manager -> specialist)
GRAPH_NODE_ID = "graph.node.id"
GRAPH_NODE_PARENT_ID = "graph.node.parent_id"

# LLM attributes
LLM_MODEL_NAME = "llm.model_name"
LLM_PROVIDER = "llm.provider"
LLM_TOKEN_PROMPT = "llm.token_count.prompt"
LLM_TOKEN_COMPLETION = "llm.token_count.completion"
LLM_TOKEN_TOTAL = "llm.token_count.total"
LLM_TOKEN_CACHE_READ = "llm.token_count.cache_read"

# Tool attributes
TOOL_NAME = "tool.name"
TOOL_PARAMETERS = "tool.parameters"
TOOL_CALL_ID = "tool_call.id"

# Guardrail attributes (Phase 7)
GUARDRAIL_OUTCOME = "guardrail.outcome"
GUARDRAIL_VIOLATIONS = "guardrail.violations"
