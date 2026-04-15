"""Preset library of well-known models per provider kind.

These are used by the admin UI ("install from preset") to populate
ModelRecord entries without the user having to type each one by hand.
"""

from __future__ import annotations

from gclaw.models.catalog import ProviderKind


PRESETS: dict[ProviderKind, dict] = {
    ProviderKind.OPENAI: {
        "base_url_default": "https://api.openai.com/v1",
        "models": [
            {
                "model_id": "gpt-4o",
                "display_name": "GPT-4o",
                "context_window": 128000,
                "max_output_tokens": 16384,
                "capabilities": {"vision": True, "tools": True},
            },
            {
                "model_id": "gpt-4o-mini",
                "display_name": "GPT-4o mini",
                "context_window": 128000,
                "capabilities": {"vision": True, "tools": True},
            },
            {
                "model_id": "o1",
                "display_name": "o1",
                "context_window": 200000,
                "capabilities": {"reasoning": True, "tools": True},
            },
            {
                "model_id": "o1-mini",
                "display_name": "o1-mini",
                "context_window": 128000,
                "capabilities": {"reasoning": True},
            },
        ],
    },
    ProviderKind.ANTHROPIC: {
        "base_url_default": "https://api.anthropic.com",
        "models": [
            {
                "model_id": "claude-opus-4-6",
                "display_name": "Claude Opus 4.6",
                "context_window": 200000,
                "capabilities": {"vision": True, "tools": True, "reasoning": True},
            },
            {
                "model_id": "claude-sonnet-4-6",
                "display_name": "Claude Sonnet 4.6",
                "context_window": 200000,
                "capabilities": {"vision": True, "tools": True},
            },
            {
                "model_id": "claude-haiku-4-5",
                "display_name": "Claude Haiku 4.5",
                "context_window": 200000,
                "capabilities": {"vision": True, "tools": True},
            },
        ],
    },
    ProviderKind.ANTHROPIC_OAUTH: {
        "base_url_default": "https://api.anthropic.com",
        "models": [
            {
                "model_id": "claude-opus-4-6",
                "display_name": "Claude Opus 4.6 (OAuth)",
                "context_window": 200000,
                "capabilities": {"vision": True, "tools": True, "reasoning": True},
            },
            {
                "model_id": "claude-sonnet-4-6",
                "display_name": "Claude Sonnet 4.6 (OAuth)",
                "context_window": 200000,
                "capabilities": {"vision": True, "tools": True},
            },
            {
                "model_id": "claude-haiku-4-5",
                "display_name": "Claude Haiku 4.5 (OAuth)",
                "context_window": 200000,
                "capabilities": {"vision": True, "tools": True},
            },
        ],
    },
    ProviderKind.GOOGLE_GEMINI: {
        "base_url_default": None,
        "models": [
            {
                "model_id": "gemini-2.5-flash",
                "display_name": "Gemini 2.5 Flash",
                "context_window": 1000000,
                "capabilities": {"vision": True, "tools": True},
            },
            {
                "model_id": "gemini-2.5-pro",
                "display_name": "Gemini 2.5 Pro",
                "context_window": 2000000,
                "capabilities": {"vision": True, "tools": True, "reasoning": True},
            },
            {
                "model_id": "gemma-3-27b-it",
                "display_name": "Gemma 3 27B (Gemini API)",
                "context_window": 128000,
                "capabilities": {},
            },
        ],
    },
    ProviderKind.OPENROUTER: {
        "base_url_default": "https://openrouter.ai/api/v1",
        "models": [
            {
                "model_id": "meta-llama/llama-3.3-70b-instruct",
                "display_name": "Llama 3.3 70B",
            },
            {
                "model_id": "nvidia/nemotron-3-super",
                "display_name": "Nemotron 3 Super",
            },
            {
                "model_id": "qwen/qwen-2.5-72b-instruct",
                "display_name": "Qwen 2.5 72B",
            },
        ],
    },
    ProviderKind.OLLAMA: {
        "base_url_default": "http://localhost:11434",
        "models": [
            {
                "model_id": "llama3.3",
                "display_name": "Llama 3.3 (local)",
            },
            {
                "model_id": "qwen2.5",
                "display_name": "Qwen 2.5 (local)",
            },
        ],
    },
    ProviderKind.GROQ: {
        "base_url_default": "https://api.groq.com/openai/v1",
        "models": [
            {
                "model_id": "llama-3.3-70b-versatile",
                "display_name": "Llama 3.3 70B",
            },
        ],
    },
}


def list_presets() -> dict:
    """Return a JSON-serializable view of the preset table."""
    return {kind.value: entry for kind, entry in PRESETS.items()}
