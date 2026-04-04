"""Tests for RemoteRunner (OpenAI-compatible API client)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from gclaw.dispatch.remote_runner import RemoteRunner


def test_remote_runner_init():
    runner = RemoteRunner(
        model="nvidia/nemotron-3-super-120b-a12b:free",
        api_base="https://openrouter.ai/api/v1",
        api_key="sk-or-test-123",
    )
    assert runner._model == "nvidia/nemotron-3-super-120b-a12b:free"
    assert runner._api_base == "https://openrouter.ai/api/v1"


@pytest.mark.asyncio
async def test_remote_runner_generate():
    runner = RemoteRunner(
        model="nvidia/nemotron-3-super-120b-a12b:free",
        api_base="https://openrouter.ai/api/v1",
        api_key="sk-or-test-123",
    )

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "The answer is 42."

    with patch.object(runner, "_client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        result = await runner.generate(
            system_prompt="You are helpful.",
            message="What is the answer?",
        )

    assert result == "The answer is 42."


@pytest.mark.asyncio
async def test_remote_runner_generate_with_history():
    runner = RemoteRunner(
        model="nvidia/nemotron-3-super-120b-a12b:free",
        api_base="https://openrouter.ai/api/v1",
        api_key="sk-or-test-123",
    )

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Follow-up answer."

    with patch.object(runner, "_client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        result = await runner.generate(
            system_prompt="You are helpful.",
            message="Follow-up question.",
            history=[
                {"role": "user", "content": "First question."},
                {"role": "assistant", "content": "First answer."},
            ],
        )

    assert result == "Follow-up answer."
    call_args = mock_client.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    assert len(messages) == 4  # system + 2 history + user
