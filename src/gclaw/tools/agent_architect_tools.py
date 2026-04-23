"""Tools for the agent-architect agent.

The architect creates new agents in-process by either:

  1. Writing markdown files into ``GCLAW_CONFIG_DIR/agents/`` and
     ``GCLAW_CONFIG_DIR/soul/`` (file-backed, requires a redeploy or
     a restart for the factory to pick them up at next boot), or

  2. Calling :func:`AgentConfigService.create_standalone` to register
     a Firestore-only standalone agent that joins the running graph
     immediately on next ``factory.build`` call.

Standalone-on-Firestore is the recommended path for runtime creation —
no redeploy, the override IS the source of truth, and the admin UI can
edit it through ``PATCH /admin/agents/{name}``.

All file-write tools refuse to escape ``GCLAW_CONFIG_DIR`` (path
traversal guard) and refuse to overwrite existing files unless
``allow_overwrite=True`` is passed explicitly. Same restriction applies
to deleting standalone agents that would clobber a baseline file.

Two extra tools — ``generate_starter_evalset`` and
``run_eval_against_draft`` — wire ADR-0006's eval feedback loop into
the architect's pipeline. They use a module-level ``AgentFactory``
handle to build ephemeral agents against drafts before registration.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any, Callable

from gclaw.config.agent_config_service import AgentConfigService

if TYPE_CHECKING:
    from gclaw.agents.factory import AgentFactory
    from gclaw.eval.judge import JudgeClient

logger = logging.getLogger(__name__)


_AGENT_NAME_OK = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
)

# Score threshold below which the architect surfaces a "needs revision"
# warning in its approval payload. Per ADR-0006: not a gate, just a
# nudge — the user always pulls the trigger.
_SCORE_WARN_THRESHOLD = 0.5


# Module-level service handle, set at startup by main.py via
# :func:`set_agent_config_service`. The tools refuse to operate when
# the service is unset — this happens in tests and in deployments
# where Firestore is unavailable.
_agent_config_service: AgentConfigService | None = None

# Module-level factory + judge model handles, set by main.py at boot.
# Keep these decoupled from the service handle above so tests can stub
# one without the other.
_agent_factory: "AgentFactory | None" = None
_judge_model_name: str = "gemini-2.5-flash"
# Optional injected judge ask function — tests stub this to avoid
# hitting Gemini. Production leaves it None and the JudgeClient builds
# its own ADK runner on first use.
_judge_ask_fn: Callable[[str], Any] | None = None


def set_agent_config_service(svc: AgentConfigService | None) -> None:
    global _agent_config_service
    _agent_config_service = svc


def set_agent_factory(factory: "AgentFactory | None") -> None:
    """Wire the AgentFactory used by ``run_eval_against_draft`` to build
    ephemeral agents."""
    global _agent_factory
    _agent_factory = factory


def set_judge_model(model_name: str) -> None:
    """Override the judge model name used by ``generate_starter_evalset``
    and ``run_eval_against_draft``. Defaults to ``gemini-2.5-flash``."""
    global _judge_model_name
    _judge_model_name = model_name or "gemini-2.5-flash"


def set_judge_ask_fn(fn: Callable[[str], Any] | None) -> None:
    """Inject a judge transport (test seam). Production leaves this
    unset and the JudgeClient builds its own ADK runner."""
    global _judge_ask_fn
    _judge_ask_fn = fn


def _require_service() -> AgentConfigService:
    if _agent_config_service is None:
        raise RuntimeError(
            "agent_config_service not configured — architect tools "
            "cannot mutate Firestore. Wire it via "
            "set_agent_config_service(svc) at app boot."
        )
    return _agent_config_service


def _require_factory() -> "AgentFactory":
    if _agent_factory is None:
        raise RuntimeError(
            "agent_factory not configured — architect eval tools cannot "
            "build ephemeral agents. Wire it via set_agent_factory(factory) "
            "at app boot."
        )
    return _agent_factory


def _build_judge_client() -> "JudgeClient":
    """Construct a JudgeClient using the module-level model name and
    optional injected ask_fn."""
    from gclaw.eval.judge import JudgeClient

    return JudgeClient(model_name=_judge_model_name, ask_fn=_judge_ask_fn)


def _config_dir() -> str:
    return os.environ.get("GCLAW_CONFIG_DIR", os.getcwd())


def _validate_name(name: str) -> None:
    if not name:
        raise ValueError("agent name is required")
    if any(c not in _AGENT_NAME_OK for c in name):
        raise ValueError(
            f"agent name {name!r} contains invalid chars; allowed: "
            "alphanumeric, '-', '_'"
        )
    if name.startswith("-") or name.startswith("_") or name.startswith("."):
        raise ValueError(
            f"agent name {name!r} cannot start with -, _, or ."
        )


def _resolve_path_within(base_subdir: str, name: str) -> str:
    """Return the absolute path for ``<config_dir>/<base_subdir>/<name>.md``.

    Refuses any name that would resolve outside the base directory
    (path-traversal guard). Used by the read/write tools below.
    """
    _validate_name(name)
    base = os.path.realpath(os.path.join(_config_dir(), base_subdir))
    target = os.path.realpath(os.path.join(base, f"{name}.md"))
    if not target.startswith(base + os.sep) and target != base:
        raise ValueError(
            f"resolved path {target!r} escapes {base!r}"
        )
    return target


# ---------- File-backed agent / soul read+write ----------


def read_agent_file(name: str) -> str:
    """Return the body of ``agents/<name>.md`` from the config dir.

    Returns a "not found" string rather than raising so the agent can
    decide how to react. Use ``list_agent_files()`` to enumerate.
    """
    try:
        path = _resolve_path_within("agents", name)
    except ValueError as e:
        return f"ERROR: {e}"
    if not os.path.isfile(path):
        return f"NOT FOUND: agents/{name}.md does not exist"
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_soul_file(name: str) -> str:
    """Return the body of ``soul/<name>.md`` from the config dir."""
    try:
        path = _resolve_path_within("soul", name)
    except ValueError as e:
        return f"ERROR: {e}"
    if not os.path.isfile(path):
        return f"NOT FOUND: soul/{name}.md does not exist"
    with open(path, encoding="utf-8") as f:
        return f.read()


def list_agent_files() -> str:
    """List every agent-definition file under ``GCLAW_CONFIG_DIR/agents``."""
    base = os.path.join(_config_dir(), "agents")
    if not os.path.isdir(base):
        return f"NOT FOUND: {base} does not exist"
    names = sorted(
        f.removesuffix(".md") for f in os.listdir(base) if f.endswith(".md")
    )
    return "\n".join(names) if names else "(no agents)"


def write_agent_file(
    name: str,
    body: str,
    allow_overwrite: bool = False,
) -> str:
    """Write a new ``agents/<name>.md`` file.

    Refuses to overwrite an existing file unless ``allow_overwrite=True``.
    The file is the agent's *baseline body*; the factory picks it up at
    next ``factory.build(name)`` call (no restart needed within a single
    process; new processes pick it up on next boot).

    Returns a one-line summary of what changed.
    """
    if not body or not body.strip():
        return "ERROR: body cannot be empty"
    try:
        path = _resolve_path_within("agents", name)
    except ValueError as e:
        return f"ERROR: {e}"
    existed = os.path.isfile(path)
    if existed and not allow_overwrite:
        return (
            f"ERROR: agents/{name}.md already exists — pass "
            "allow_overwrite=True to replace"
        )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body if body.endswith("\n") else body + "\n")
    verb = "overwrote" if existed else "created"
    return f"OK: {verb} agents/{name}.md ({len(body)} chars)"


def write_soul_file(
    name: str,
    body: str,
    allow_overwrite: bool = False,
) -> str:
    """Write a new ``soul/<name>.md`` file. Same rules as ``write_agent_file``."""
    if not body or not body.strip():
        return "ERROR: body cannot be empty"
    try:
        path = _resolve_path_within("soul", name)
    except ValueError as e:
        return f"ERROR: {e}"
    existed = os.path.isfile(path)
    if existed and not allow_overwrite:
        return (
            f"ERROR: soul/{name}.md already exists — pass "
            "allow_overwrite=True to replace"
        )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body if body.endswith("\n") else body + "\n")
    verb = "overwrote" if existed else "created"
    return f"OK: {verb} soul/{name}.md ({len(body)} chars)"


# ---------- Standalone (Firestore-only) agent registration ----------


def register_standalone_agent(
    agent_name: str,
    body: str,
    display_name: str = "",
    description: str = "",
    soul_overlay: str = "",
    model_primary: str = "",
) -> str:
    """Register a new standalone agent in Firestore (no .md file).

    Standalone agents have no baseline file and the override IS the
    source of truth. They join the running graph on next
    ``factory.build`` call — no redeploy needed. Refuses if an agent
    with the same name already exists in either the file system
    (would shadow the baseline) or Firestore (would collide with an
    existing override).

    Args:
        agent_name: kebab-case identifier; used for routing.
        body: full system-prompt body text. Required.
        display_name: human-readable name for the admin UI.
        description: one-line summary of what the agent does.
        soul_overlay: agent-specific personality on top of soul/base.md.
        model_primary: catalog model ref. Examples:
          ``"gemini-2.5-flash"`` (bare id, ambiguous if multiple
          providers list it),
          ``"Anthropic/claude-haiku-4-5"`` (provider/model, explicit).

    Returns: confirmation with the new agent_name.
    """
    _validate_name(agent_name)
    svc = _require_service()
    try:
        override = svc.create_standalone(
            agent_name=agent_name,
            body=body,
            display_name=display_name or None,
            description=description or None,
            soul_overlay=soul_overlay or None,
            model_primary=model_primary or None,
        )
    except ValueError as e:
        return f"ERROR: {e}"
    return (
        f"OK: standalone agent {override.agent_name!r} registered "
        f"(model={(override.model.primary or '<router-default>')})"
    )


def update_agent_model(agent_name: str, primary: str) -> str:
    """Patch an existing agent's primary model.

    Works for both standalone and file-backed agents. The factory
    re-resolves on the next ``build`` call so the change is live
    without a restart for in-process callers — but already-built
    LlmAgent instances in memory keep the old model until the
    process recycles. Bounce the service to force a clean rebuild.
    """
    _validate_name(agent_name)
    if not primary:
        return "ERROR: primary model id is required"
    svc = _require_service()
    try:
        override = svc.upsert_override(
            agent_name, {"model": {"primary": primary}}
        )
    except ValueError as e:
        return f"ERROR: {e}"
    return (
        f"OK: {agent_name} model.primary set to {override.model.primary!r}"
    )


def list_registered_agents() -> str:
    """List every agent the platform knows about, one per line.

    Includes both baseline (file-backed) and standalone (Firestore-only)
    agents. Each line: ``<name> [baseline|standalone|override-on-baseline]
    model=<ref>``.
    """
    svc = _require_service()
    rows: list[str] = []
    for entry in svc.list_agents():
        if entry.get("is_standalone"):
            kind = "standalone"
        elif entry.get("has_override"):
            kind = "override-on-baseline"
        else:
            kind = "baseline"
        model = entry.get("model_ref") or "<router-default>"
        rows.append(f"{entry['name']} [{kind}] model={model}")
    return "\n".join(rows) if rows else "(no agents)"


# ---------- Eval feedback loop (ADR-0006) ----------

# Tool registry for ``run_eval_against_draft``. Maps tool function
# ``__name__`` → callable. Built lazily on first lookup so the import
# graph stays clean (this module otherwise wouldn't import the manager
# tool modules). v1 limitation: we can only resolve tools that are
# already bound to one of the existing managers — full
# tool-binding-by-name (where overrides store ``tools: ["..."]`` and
# the factory binds them generically) is ADR-0002's "Open question".
_TOOL_REGISTRY: dict[str, Callable] | None = None


def _build_tool_registry() -> dict[str, Callable]:
    """Index every public manager tool by ``__name__`` for v1 lookup.

    Includes the architect's own tools (so the architect can build
    sub-architects for eval purposes) plus the union of every manager's
    domain tools. Pulled together at first use to avoid the cost on
    cold starts that don't touch the eval path.
    """
    from gclaw.tools import (
        comms_tools,
        context_tools,
        dev_tools,
        home_tools,
        image_gen_tools,
        postiz_tools,
        research_tools,
        user_profile_tools,
        workspace_tools,
    )

    registry: dict[str, Callable] = {}

    # Architect's own tools (sans the eval ones — recursing the eval
    # loop into a draft is out of scope for v1).
    for name in (
        "read_agent_file",
        "read_soul_file",
        "list_agent_files",
        "list_registered_agents",
        "write_agent_file",
        "write_soul_file",
        "register_standalone_agent",
        "update_agent_model",
    ):
        fn = globals().get(name)
        if callable(fn):
            registry[name] = fn

    for module in (
        workspace_tools,
        dev_tools,
        home_tools,
        comms_tools,
        research_tools,
        postiz_tools,
        image_gen_tools,
        user_profile_tools,
        context_tools,
    ):
        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue
            attr = getattr(module, attr_name)
            if not callable(attr):
                continue
            # Skip module-level setters (set_*), error helpers (_err),
            # and anything that doesn't look like a public tool. The
            # filter is intentionally loose — manager tools are plain
            # async/sync functions, not classes or partials.
            if attr_name.startswith("set_"):
                continue
            registry.setdefault(attr_name, attr)
    return registry


def _resolve_tool(name: str) -> Callable:
    """Look up a tool callable by its declared name.

    v1 limitation: only tools already bound to one of the managers
    (workspace, dev, home, comms, research, postiz, image_gen,
    user_profile, context) plus the architect's own tools are
    resolvable. Raises ``ValueError`` for unknown names so the
    architect surfaces "I can't grant tool X" up to the user.
    """
    global _TOOL_REGISTRY
    if _TOOL_REGISTRY is None:
        _TOOL_REGISTRY = _build_tool_registry()
    fn = _TOOL_REGISTRY.get(name)
    if fn is None:
        known = ", ".join(sorted(_TOOL_REGISTRY.keys())[:20])
        raise ValueError(
            f"unknown tool name {name!r}; v1 only supports tools "
            f"already bound to a manager. Known examples: {known}..."
        )
    return fn


def _evalsets_dir() -> str:
    """Return the directory where starter evalsets are written.

    Defaults to ``tests/eval/evalsets/`` relative to the current
    working directory — matches the layout in ADR-0005. Override via
    ``GCLAW_EVALSETS_DIR`` for ephemeral test runs.
    """
    return os.environ.get(
        "GCLAW_EVALSETS_DIR", os.path.join("tests", "eval", "evalsets")
    )


_STARTER_EVALSET_PROMPT = """\
You are writing test cases for a brand-new gclaw agent.

Agent name: {agent_name}
Agent body:
\"\"\"
{body}
\"\"\"

Tools available to the agent:
{tools_block}

Write exactly {case_count} test cases that exercise this agent's
described capabilities. Each case must be a JSON object with these
keys:

  - "case_id": kebab-case unique id
  - "input": a realistic user request the agent should handle
  - "agent_name": "{agent_name}"
  - "expected_tool_uses": list of {{"name": str, "args_match": {{...}}}}
    objects describing which tools the agent should call. ``args_match``
    values are regex patterns (use ".*" when you don't care).
  - "expected_response": one of
      * {{"match_type": "rubric_based_final_response_quality_v1", "rubric": "..."}}
      * {{"match_type": "final_response_match_v2", "expected": "...",
          "rubric": "..."}}

Reply with a single JSON object of the form:

{{"cases": [<case>, <case>, ...]}}

No prose outside the JSON. No markdown fences.
"""


def _parse_starter_response(raw: str) -> list[dict[str, Any]]:
    """Pull the ``cases`` list out of a (possibly fenced) judge reply.

    Tolerates ``` fences and surrounding prose for cheap; raises
    ``ValueError`` if no parsable JSON object with a ``cases`` list
    can be found.
    """
    import re

    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # First, try the whole blob.
    candidates = [text]
    # Fall back to the largest brace block.
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        candidates.append(brace_match.group(0))
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("cases"), list):
            return data["cases"]
    raise ValueError(
        "could not parse starter evalset cases from judge reply: "
        f"{raw[:200]!r}"
    )


async def generate_starter_evalset(
    agent_name: str,
    body: str,
    tools_declared: list[str],
    case_count: int = 5,
) -> str:
    """Use the orchestrator's judge model to draft an evalset.

    Produces a JSON evalset with ``case_count`` plausible test cases
    derived from the agent's body + tool list, saves it to
    ``tests/eval/evalsets/<agent_name>.json`` (or the path under
    ``GCLAW_EVALSETS_DIR`` when set), and returns the path.

    The architect calls this at step 5 of the pipeline (per ADR-0006);
    the user can edit the resulting file before approving the agent.

    Args:
        agent_name: kebab-case identifier; used for the evalset name
            and output filename.
        body: agent body markdown (the same content the architect
            staged via ``context_write``).
        tools_declared: list of tool ``__name__`` strings the draft
            agent expects to use.
        case_count: how many cases to generate (default 5; the ADR
            recommends 3–5).

    Returns:
        On success: ``"OK: wrote <path> (N cases)"``.
        On failure: ``"ERROR: <reason>"`` — the architect can decide
        whether to retry or fall back to vibes-only review.
    """
    _validate_name(agent_name)
    if case_count < 1 or case_count > 20:
        return f"ERROR: case_count {case_count} out of range (1..20)"
    if not body or not body.strip():
        return "ERROR: body cannot be empty"

    tools_block = (
        "\n".join(f"- {t}" for t in tools_declared)
        if tools_declared else "(none)"
    )
    prompt = _STARTER_EVALSET_PROMPT.format(
        agent_name=agent_name,
        body=body,
        tools_block=tools_block,
        case_count=case_count,
    )

    judge = _build_judge_client()
    try:
        verdict = await judge.ask(
            input_=f"starter-evalset::{agent_name}",
            response="",
            rubric=f"starter-evalset::case_count={case_count}",
            prompt=prompt,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "starter evalset judge call failed for %s: %s",
            agent_name,
            e,
            exc_info=True,
        )
        return f"ERROR: judge call failed: {type(e).__name__}: {e}"

    raw = verdict.raw or ""
    try:
        cases = _parse_starter_response(raw)
    except ValueError as e:
        return f"ERROR: {e}"
    if not cases:
        return "ERROR: judge returned an empty cases list"

    evalset_doc = {
        "name": agent_name,
        "description": (
            f"Starter evalset auto-generated for {agent_name} "
            f"({len(cases)} cases)."
        ),
        "judge_model": _judge_model_name,
        "cases": cases,
    }
    out_dir = _evalsets_dir()
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{agent_name}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(evalset_doc, f, indent=2)
        f.write("\n")
    logger.info(
        "generated starter evalset for %s: %s (%d cases)",
        agent_name,
        out_path,
        len(cases),
    )
    return f"OK: wrote {out_path} ({len(cases)} cases)"


async def run_eval_against_draft(
    agent_name: str,
    body: str,
    soul_overlay: str,
    tools_declared: list[str],
    evalset_path: str,
) -> str:
    """Build an ephemeral agent from the draft, run an evalset, and
    return a formatted score table (ADR-0006 step 5).

    Internally:

      1. Resolves each tool name in ``tools_declared`` via the v1 tool
         registry. Unknown names abort with an ``ERROR:`` string so the
         architect can surface them to the user.
      2. Builds the ephemeral agent via ``factory.build_transient`` —
         no Firestore writes, no memory recall callback.
      3. Runs the evalset with a JudgeClient targeting the orchestrator's
         model. Each case spins up a fresh ``AgentRunner`` against the
         transient agent.
      4. Renders the result block per ADR-0006's "Approval payload
         shape" and returns it as a multi-line string for the architect
         to paste into its summary.

    v1 limitation: ``tools_declared`` may only list tools already bound
    to one of the existing managers (or the architect's own toolset).
    Net-new tools require a ``dev-mgr`` source-tree edit before they
    can be referenced here — see ADR-0002 "Open questions".

    Args:
        agent_name: identifier for the draft.
        body: full agent body markdown.
        soul_overlay: name of an existing soul overlay file (under
            ``soul/``) or empty string for the base soul only.
        tools_declared: list of tool function names. Each must resolve
            via ``_resolve_tool``.
        evalset_path: filesystem path to the evalset JSON to run.
            Typically the path returned by ``generate_starter_evalset``.

    Returns:
        On success: a multi-line formatted score table block.
        On failure: ``"ERROR: <reason>"``.
    """
    _validate_name(agent_name)
    if not body or not body.strip():
        return "ERROR: body cannot be empty"

    # Factory must be wired before we touch the file system or the
    # tool registry — keeps the failure mode surfaced via RuntimeError
    # at boot-misconfig time instead of silently returning ERROR
    # strings that look like normal eval results.
    factory = _require_factory()

    # Resolve tools next so the failure mode is "I don't know that
    # tool" and not "the eval crashed half-way through".
    try:
        tool_callables = [_resolve_tool(n) for n in tools_declared]
    except ValueError as e:
        return f"ERROR: {e}"

    # Load the evalset — fail fast if it's malformed.
    from gclaw.eval.evalset import Evalset

    try:
        evalset = Evalset.from_json(evalset_path)
    except FileNotFoundError:
        return f"ERROR: evalset not found at {evalset_path}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: failed to load evalset: {type(e).__name__}: {e}"
    overlay = soul_overlay or None
    transient_agent = factory.build_transient(
        agent_name=agent_name,
        body=body,
        soul_overlay=overlay,
        tools=tool_callables,
    )

    # Wire an EvalRunner that builds a fresh AgentRunner around the
    # transient agent for every case (ADK runners are cheap to
    # construct; sharing one across cases would muddy session state).
    from google.adk.sessions import InMemorySessionService

    from gclaw.dispatch.runner import AgentRunner
    from gclaw.eval.evalset_runner import EvalRunner

    session_service = InMemorySessionService()

    def _runner_builder(_case):
        return AgentRunner(
            agent=transient_agent,
            app_name="gclaw-architect-eval",
            session_service=session_service,
        )

    judge = _build_judge_client()
    runner = EvalRunner(
        factory=None,
        judge=judge,
        session_service=session_service,
        app_name="gclaw-architect-eval",
        runner_builder=_runner_builder,
    )

    try:
        result = await runner.run_evalset(evalset)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "run_eval_against_draft failed for %s: %s",
            agent_name,
            e,
            exc_info=True,
        )
        return (
            f"ERROR: eval run crashed: {type(e).__name__}: {e}"
        )

    return _format_eval_block(
        agent_name=agent_name,
        evalset=evalset,
        result=result,
        judge_model=_judge_model_name,
        tools_declared=tools_declared,
    )


def _format_eval_block(
    *,
    agent_name: str,
    evalset: Any,
    result: Any,
    judge_model: str,
    tools_declared: list[str],
) -> str:
    """Render the multi-line "DRAFT READY" block from ADR-0006.

    Walks ``result.metric_averages`` and emits one line per metric,
    appending a warning when any score is below ``_SCORE_WARN_THRESHOLD``.
    """
    lines: list[str] = [f"DRAFT READY: {agent_name}", ""]
    tools_str = ", ".join(tools_declared) if tools_declared else "(none)"
    lines.append(f"  Tools:   {tools_str}")
    lines.append("")
    case_count = len(evalset.cases)
    lines.append(
        f"  Eval ({case_count} cases, judge={judge_model}):"
    )
    averages = result.metric_averages or {}
    if not averages:
        lines.append("    (no metrics applied — check evalset shape)")
    else:
        # Stable, ADR-shaped order: trajectory, response, hallucinations,
        # then anything else.
        preferred = [
            "tool_trajectory_avg_score",
            "final_response_match_v2",
            "rubric_based_final_response_quality_v1",
            "rubric_based_tool_use_quality_v1",
            "response_match_score",
            "hallucinations_v1",
            "safety_v1",
        ]
        seen: set[str] = set()
        for name in preferred:
            if name in averages:
                lines.append(_format_metric_line(name, averages[name]))
                seen.add(name)
        for name, score in averages.items():
            if name in seen:
                continue
            lines.append(_format_metric_line(name, score))

    failing = [
        (name, score) for name, score in averages.items()
        if score < _SCORE_WARN_THRESHOLD
    ]
    lines.append("")
    if failing:
        for name, score in failing:
            lines.append(
                f"  WARN: {name} ({score:.2f}) below threshold "
                f"({_SCORE_WARN_THRESHOLD:.2f})."
            )
        lines.append(
            "  Recommendation: REVISE before approving."
        )
    else:
        lines.append(
            "  All scores meet threshold; recommended: APPROVE."
        )
    return "\n".join(lines)


def _format_metric_line(name: str, score: float) -> str:
    """Right-pad a metric name to 36 chars and render its score to 2dp."""
    return f"    {name:<36s} {score:.2f}"
