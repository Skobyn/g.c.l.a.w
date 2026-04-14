"""Usage recorder — thin, fire-and-forget wrapper over UsageRepo.

The recorder MUST NOT raise into the main call path. Every public
``record_*`` method catches and logs any exception raised by the
underlying repo. Callers treat these as best-effort.

A module-level singleton is exposed via ``get_recorder()`` / ``set_recorder()``
matching the pattern used by heartbeat's event bus.
"""

from __future__ import annotations

import contextlib
import logging
import time
from typing import Callable

from gclaw.firestore.usage_repo import UsageRepo
from gclaw.models.usage import UsageEvent, UsageKind

logger = logging.getLogger(__name__)


class UsageRecorder:
    """Async-safe, exception-safe wrapper over :class:`UsageRepo`."""

    def __init__(
        self,
        repo: UsageRepo | None,
        *,
        enabled: bool = True,
        cost_lookup: Callable[[str, int, int], float | None] | None = None,
    ) -> None:
        self._repo = repo
        self._enabled = enabled and repo is not None
        self._cost_lookup = cost_lookup

    @property
    def enabled(self) -> bool:
        return self._enabled

    # -- low-level --------------------------------------------------------

    def _emit(self, event: UsageEvent) -> None:
        if not self._enabled:
            return
        try:
            assert self._repo is not None
            self._repo.record(event)
        except Exception:
            logger.warning(
                "usage: failed to record %s/%s", event.kind.value, event.name,
                exc_info=True,
            )

    # -- public recorders -------------------------------------------------

    def record_model_call(
        self,
        *,
        model_id: str,
        provider_id: str | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        cost_usd: float | None = None,
        duration_ms: int = 0,
        success: bool = True,
        error: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        caller: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        if (
            cost_usd is None
            and self._cost_lookup is not None
            and tokens_in is not None
            and tokens_out is not None
        ):
            try:
                cost_usd = self._cost_lookup(model_id, tokens_in, tokens_out)
            except Exception:
                logger.warning(
                    "usage: cost_lookup failed for %s", model_id, exc_info=True,
                )
                cost_usd = None
        self._emit(UsageEvent(
            kind=UsageKind.MODEL,
            name=model_id,
            provider_id=provider_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            success=success,
            error=error,
            user_id=user_id,
            session_id=session_id,
            caller=caller,
            metadata=metadata or {},
        ))

    def record_agent_invoke(
        self,
        *,
        agent_name: str,
        caller: str | None = None,
        duration_ms: int = 0,
        success: bool = True,
        error: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        self._emit(UsageEvent(
            kind=UsageKind.AGENT,
            name=agent_name,
            caller=caller,
            duration_ms=duration_ms,
            success=success,
            error=error,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata or {},
        ))

    def record_skill_use(
        self,
        *,
        skill_name: str,
        agent_name: str | None = None,
        duration_ms: int = 0,
        success: bool = True,
        error: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        self._emit(UsageEvent(
            kind=UsageKind.SKILL,
            name=skill_name,
            caller=agent_name,
            duration_ms=duration_ms,
            success=success,
            error=error,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata or {},
        ))

    def record_tool_call(
        self,
        *,
        tool_name: str,
        agent_name: str | None = None,
        duration_ms: int = 0,
        success: bool = True,
        error: str | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        self._emit(UsageEvent(
            kind=UsageKind.TOOL,
            name=tool_name,
            caller=agent_name,
            duration_ms=duration_ms,
            success=success,
            error=error,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata or {},
        ))


# --- module-level singleton -------------------------------------------------

_recorder: UsageRecorder | None = None


def set_recorder(recorder: UsageRecorder | None) -> None:
    global _recorder
    _recorder = recorder


def get_recorder() -> UsageRecorder:
    """Return the active recorder, or a no-op one if none is configured."""
    global _recorder
    if _recorder is None:
        _recorder = UsageRecorder(repo=None, enabled=False)
    return _recorder


# --- context helper ---------------------------------------------------------


@contextlib.contextmanager
def timed_record(record_fn: Callable[..., None], **kwargs):
    """Time a block and forward the measurement to ``record_fn``.

    Usage::

        with timed_record(
            recorder.record_tool_call,
            tool_name="x",
            agent_name="y",
        ) as ctx:
            result = do_work()
            ctx["metadata"]["result_size"] = len(result)

    Captures wall-clock duration, sets ``success=False`` + ``error``
    on exception, and always calls ``record_fn`` exactly once.
    """
    metadata: dict = dict(kwargs.pop("metadata", {}) or {})
    ctx: dict = {"metadata": metadata}
    start = time.perf_counter()
    success = True
    error: str | None = None
    try:
        yield ctx
    except Exception as e:  # noqa: BLE001 — pass-through after recording
        success = False
        error = f"{type(e).__name__}: {e}"
        raise
    finally:
        duration_ms = int((time.perf_counter() - start) * 1000)
        try:
            record_fn(
                duration_ms=duration_ms,
                success=success,
                error=error,
                metadata=ctx.get("metadata", metadata),
                **kwargs,
            )
        except Exception:
            logger.warning("usage: timed_record finalize failed", exc_info=True)
