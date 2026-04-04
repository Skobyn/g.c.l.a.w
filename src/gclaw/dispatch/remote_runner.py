"""Run agent turns via OpenAI-compatible APIs (OpenRouter, NVIDIA API, etc.)."""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class RemoteRunner:
    """Calls an OpenAI-compatible API for text generation.

    Used for non-Gemini models (Nemotron via OpenRouter, etc.) that
    can't run through ADK's native Runner.
    """

    def __init__(
        self,
        model: str,
        api_base: str,
        api_key: str,
    ) -> None:
        self._model = model
        self._api_base = api_base
        self._client = AsyncOpenAI(
            base_url=api_base,
            api_key=api_key,
        )

    async def generate(
        self,
        system_prompt: str,
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]

        if history:
            messages.extend(history)

        messages.append({"role": "user", "content": message})

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
        )

        return response.choices[0].message.content
