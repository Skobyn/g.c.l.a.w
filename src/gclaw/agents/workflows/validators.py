"""Custom BaseAgent implementations used as final gates in composed workflows."""

from __future__ import annotations

from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from google.genai.types import Content, Part


class ValidateCommitMsg(BaseAgent):
    """Final gate in the CommitMessageWorkflow.

    Reads session state:
      - review_status: "pass" or "fail: <reason>" (written by the reviewer)
      - commit_draft:  the drafted commit message (written by the drafter)

    Yields a single Event containing either the approved draft or an
    actionable rejection with the reviewer's feedback.
    """

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        status = (state.get("review_status") or "").strip()
        draft = (state.get("commit_draft") or "").strip()

        status_lower = status.lower()

        if status_lower.startswith("pass"):
            text = f"Commit message approved:\n\n{draft}"
        else:
            if status_lower.startswith("fail:"):
                reason = status[len("fail:"):].strip()
            else:
                reason = status or "No review status found in session state."
            text = (
                f"Commit message rejected.\n\n"
                f"Draft:\n{draft or '(no draft found)'}\n\n"
                f"Reason: {reason}\n\n"
                f"Fix the issues and re-run the workflow."
            )

        yield Event(
            author=self.name,
            content=Content(role="model", parts=[Part(text=text)]),
        )
