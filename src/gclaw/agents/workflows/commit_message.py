"""Commit message composed workflow — draft + reviewer + validate."""

from __future__ import annotations

from typing import Any

from google.adk.agents import LlmAgent, SequentialAgent

from gclaw.agents.workflows.validators import ValidateCommitMsg
from gclaw.models.model_config import TaskProfile
from gclaw.routing.router import ModelRouter


def build_commit_message_workflow(
    *,
    dev_tools: list[Any],
    router: ModelRouter | None,
    default_model: str = "gemini-2.5-flash",
) -> SequentialAgent:
    """Build the commit message workflow.

    Draft -> Reviewer -> Validate sequence. The draft specialist uses the
    CODE_GENERATION task profile (Nemotron via LiteLlm when the router is
    wired). The reviewer uses the default (Gemini Flash) for speed. Validate
    is a custom BaseAgent that reads session state and emits the final result.
    """
    draft_model: Any = (
        router.build_adk_model_for_profile(TaskProfile.CODE_GENERATION)
        if router is not None
        else default_model
    )

    draft = LlmAgent(
        name="commit_draft_specialist",
        model=draft_model,
        description="Drafts a commit message from the current diff.",
        instruction=(
            "You draft Conventional Commits messages from a git diff.\n\n"
            "1. Call get_current_diff to read the staged/unstaged diff.\n"
            "2. Determine the change type — feat, fix, docs, refactor, test, or chore.\n"
            "3. Write a commit message with this shape:\n"
            "   - Subject line: '<type>: <short imperative description>' (<=72 chars, no trailing period).\n"
            "   - Optional body: blank line separator, explains *why*, not *what*.\n"
            "4. Output only the commit message. No preamble, no code fences."
        ),
        tools=dev_tools,
        output_key="commit_draft",
    )

    reviewer = LlmAgent(
        name="style_reviewer_specialist",
        model=default_model,
        description="Scores a commit message draft against commit conventions.",
        instruction=(
            "You review commit message drafts. The draft is in session state as {commit_draft}.\n\n"
            "Check these rules:\n"
            "1. Subject uses a Conventional Commits prefix "
            "(feat/fix/docs/refactor/test/chore/build/ci/perf/style).\n"
            "2. Subject is <= 72 chars.\n"
            "3. Subject uses imperative mood ('add X', not 'adds' or 'added').\n"
            "4. If a body exists, a blank line separates it from the subject.\n"
            "5. No trailing period on the subject line.\n\n"
            "Output exactly one of:\n"
            "- 'pass' — if all rules are satisfied\n"
            "- 'fail: <brief explanation>' — otherwise"
        ),
        output_key="review_status",
    )

    return SequentialAgent(
        name="CommitMessageWorkflow",
        sub_agents=[
            draft,
            reviewer,
            ValidateCommitMsg(name="validate_commit_msg"),
        ],
    )
