"""Admin API routes for the Agent Dashboard and management views.

Provides endpoints for:
- Agent listing and status
- Heartbeat log viewing
- Soul file read/write
- Skills listing
- Memory search, list, and delete
- Cron management
"""

from __future__ import annotations

import os
import logging
import re
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

# Firestore document IDs must survive `collection.document(name)` — this
# rules out `/`, `.`, `..`, and `__x__` forms. The new skill CRUD surface
# is the only write path; keep the charset conservative so we don't
# produce records unreachable via the paired `{skill_name}` routes.
_SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

from gclaw.auth.dependencies import get_current_user_id
from gclaw.config.loader import ConfigLoader
from gclaw.heartbeat.events import get_event_bus
from gclaw.heartbeat.log import HeartbeatLogRepo
from gclaw.heartbeat.reason import WakeReason
from gclaw.memory.service import MemoryService
from gclaw.models.memory import MemoryScope
from gclaw.skill.registry import SkillRegistry
from gclaw.cron.service import CronService
from gclaw.cron.delivery import CronDeliveryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")

_config_loader: ConfigLoader | None = None
_hb_repo_factory: Callable[[str], HeartbeatLogRepo] | None = None
_skill_registry: SkillRegistry | None = None
_memory_service: MemoryService | None = None
_cron_service: CronService | None = None
_cron_delivery_service: CronDeliveryService | None = None
_heartbeat_registry: object | None = None
_system_config_repo: object | None = None


def init_admin_router(
    config_loader: ConfigLoader,
    heartbeat_log_repo_factory: Callable[[str], HeartbeatLogRepo] | None = None,
    skill_registry: SkillRegistry | None = None,
    memory_service: MemoryService | None = None,
    cron_service: CronService | None = None,
    heartbeat_registry: object | None = None,
    cron_delivery_service: CronDeliveryService | None = None,
    system_config_repo: object | None = None,
) -> APIRouter:
    global _config_loader, _hb_repo_factory, _skill_registry
    global _memory_service, _cron_service, _heartbeat_registry
    global _cron_delivery_service, _system_config_repo
    _config_loader = config_loader
    _hb_repo_factory = heartbeat_log_repo_factory
    _skill_registry = skill_registry
    _memory_service = memory_service
    _cron_service = cron_service
    _heartbeat_registry = heartbeat_registry
    _cron_delivery_service = cron_delivery_service
    _system_config_repo = system_config_repo
    return router


# --- Agents ---
#
# Agent listing + CRUD has moved to ``agent_config_routes.py`` which is
# service-backed (Firestore overrides). When that service isn't wired
# the app still mounts a fallback ``GET /admin/agents`` that scans the
# .md directory — so tests and callers that expect the legacy shape
# keep working.


class AgentInfo(BaseModel):
    name: str
    has_soul_overlay: bool


def _legacy_list_agents() -> list[dict]:
    """Scan-only listing used when no AgentConfigService is wired."""
    agents_dir = os.path.join(_config_loader._config_dir, "agents")
    result = []
    if os.path.isdir(agents_dir):
        for fname in sorted(os.listdir(agents_dir)):
            if fname.endswith(".md"):
                agent_name = fname.removesuffix(".md")
                soul_dir = os.path.join(_config_loader._config_dir, "soul")
                has_overlay = os.path.isfile(
                    os.path.join(soul_dir, f"{agent_name.split('-')[0]}.md")
                )
                result.append({
                    "name": agent_name,
                    "has_soul_overlay": has_overlay,
                })
    return result


@router.get("/agents")
def list_agents_legacy(user_id: str = Depends(get_current_user_id)):
    """Legacy fallback. Overridden by agent_config_routes when the
    AgentConfigService is wired into ``create_app``."""
    return _legacy_list_agents()


# --- Heartbeat Logs ---


@router.get("/heartbeat-logs")
def list_heartbeat_logs(
    limit: int = 20,
    user_id: str = Depends(get_current_user_id),
):
    """List recent heartbeat log entries."""
    repo = _hb_repo_factory(user_id)
    logs = repo.list_recent(limit=limit)
    return [log.model_dump(mode="json") for log in logs]


# --- Heartbeat Events (in-process pubsub) ---


@router.get("/heartbeat/events")
def list_heartbeat_events(
    limit: int = 50,
    agent_id: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    """Return recent heartbeat events from the in-process ring buffer.

    Newest first. Optionally filter to a single agent_id.
    """
    bus = get_event_bus()
    events = bus.recent(limit=limit, agent_id=agent_id)
    return [e.model_dump(mode="json") for e in events]


@router.get("/heartbeat/health")
def heartbeat_health(user_id: str = Depends(get_current_user_id)):
    """Per-agent summary of the most recent heartbeat event."""
    bus = get_event_bus()
    # Iterate full ring newest-first; collect first seen per agent.
    events = bus.recent(limit=10_000)
    seen: dict[str, dict] = {}
    for e in events:
        if e.agent_id in seen:
            continue
        seen[e.agent_id] = {
            "agent_id": e.agent_id,
            "last_event_at": e.timestamp.isoformat(),
            "last_status": e.status.value,
            "last_reason": e.reason.value,
            "last_preview": e.preview,
        }
    return {"agents": list(seen.values())}


@router.post("/heartbeat/trigger")
async def trigger_heartbeat(
    agent_id: str = "orchestrator",
    user_id: str = Depends(get_current_user_id),
):
    """Manually trigger a single heartbeat cycle for ``agent_id``.

    Returns the emitted HeartbeatEvent (if any) alongside the raw run
    result so the admin UI can surface the outcome immediately.
    """
    if _heartbeat_registry is None:
        raise HTTPException(
            status_code=503, detail="Heartbeat registry not configured"
        )
    service = _heartbeat_registry.get(agent_id)  # type: ignore[attr-defined]
    if service is None:
        raise HTTPException(
            status_code=404,
            detail=f"No heartbeat for agent {agent_id!r}",
        )
    try:
        result = await service.run(reason=WakeReason.MANUAL)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Heartbeat failed: {e}",
        )

    bus = get_event_bus()
    recent = bus.recent(limit=1, agent_id=agent_id)
    event_payload = (
        recent[0].model_dump(mode="json") if recent else None
    )
    status = result.get("status")
    return {
        "event": event_payload,
        "result": {
            "orchestrator_response": result.get("orchestrator_response", ""),
            "actions_taken": result.get("actions_taken", []),
            "tasks_created": result.get("tasks_created", []),
            "status": status.value if hasattr(status, "value") else status,
        },
    }


# --- Soul Files ---


@router.get("/soul/{name}")
def get_soul_file(
    name: str,
    user_id: str = Depends(get_current_user_id),
):
    """Read a soul file by name (e.g., 'base', 'workspace').

    Also accepts agent names like 'dev-mgr' — maps to the soul
    overlay by taking the first segment before the hyphen ('dev').
    """
    try:
        content = _config_loader.load_soul(name)
        return {"name": name, "content": content}
    except FileNotFoundError:
        # Try mapping agent name → soul overlay (e.g. dev-mgr → dev)
        if "-" in name:
            overlay = name.split("-")[0]
            try:
                content = _config_loader.load_soul(overlay)
                return {"name": overlay, "content": content}
            except FileNotFoundError:
                pass
        raise HTTPException(status_code=404, detail=f"Soul file '{name}' not found")


class SoulUpdateRequest(BaseModel):
    content: str


@router.put("/soul/{name}")
def update_soul_file(
    name: str,
    req: SoulUpdateRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Update a soul file's content.

    Accepts agent names (dev-mgr → dev) like the GET endpoint.
    """
    resolved = name
    soul_path = os.path.join(_config_loader._config_dir, "soul", f"{name}.md")
    if not os.path.isfile(soul_path) and "-" in name:
        resolved = name.split("-")[0]
        soul_path = os.path.join(_config_loader._config_dir, "soul", f"{resolved}.md")
    if not os.path.isfile(soul_path):
        raise HTTPException(status_code=404, detail=f"Soul file '{name}' not found")
    with open(soul_path, "w") as f:
        f.write(req.content)
    return {"name": name, "status": "updated"}


# --- System: Timezone ---


@router.get("/system/timezone")
def get_system_timezone(user_id: str = Depends(get_current_user_id)):
    """Return the currently-active user timezone (IANA name)."""
    tz = (
        _config_loader.get_user_timezone()
        if _config_loader is not None
        else "UTC"
    )
    return {"timezone": tz}


class TimezoneUpdateRequest(BaseModel):
    timezone: str


@router.put("/system/timezone")
def update_system_timezone(
    req: TimezoneUpdateRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Hot-swap the user timezone.

    Validates the IANA name against zoneinfo, persists to
    ``config/system`` in Firestore so the value survives restarts,
    then pushes the value into the live ConfigLoader and CronService
    so subsequent prompts and crons pick it up immediately.
    """
    tz = (req.timezone or "").strip()
    if not tz:
        raise HTTPException(status_code=400, detail="timezone is required")
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(tz)  # validates; raises on unknown name
    except Exception:
        raise HTTPException(
            status_code=400, detail=f"unknown IANA timezone: {tz!r}"
        )

    if _system_config_repo is not None:
        try:
            _system_config_repo.set_field("user_timezone", tz)
        except Exception:
            logger.warning(
                "system-config: failed to persist timezone", exc_info=True
            )

    if _config_loader is not None:
        _config_loader.set_user_timezone(tz)
    if _cron_service is not None:
        try:
            _cron_service.set_default_timezone(tz)
        except Exception:
            logger.warning(
                "cron-service: set_default_timezone failed", exc_info=True
            )

    return {"timezone": tz, "status": "updated"}


# --- User Profile ---


@router.get("/user-profile")
def get_user_profile(user_id: str = Depends(get_current_user_id)):
    """Read the shared user-profile markdown (``<config_dir>/user.md``).

    Returns an empty string when the file doesn't exist so the UI can
    render its starter template. The loader also gracefully handles a
    missing file at prompt-build time.
    """
    content = _config_loader.load_user_profile()
    return {"content": content}


class UserProfileUpdateRequest(BaseModel):
    content: str


@router.put("/user-profile")
def update_user_profile(
    req: UserProfileUpdateRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Write the shared user-profile markdown. Creates the file when
    missing so a blank fresh install still lands somewhere writable."""
    path = os.path.join(_config_loader._config_dir, "user.md")
    with open(path, "w") as f:
        f.write(req.content)
    return {"status": "updated", "bytes": len(req.content)}


# --- Skills ---


@router.get("/skills")
def list_skills(user_id: str = Depends(get_current_user_id)):
    """List all registered skills."""
    skills = _skill_registry.list_all()
    return [s.model_dump(mode="json") for s in skills]


@router.get("/skills/{skill_name}")
def get_skill(
    skill_name: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get a single skill by name."""
    skill = _skill_registry.get(skill_name)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
    return skill.model_dump(mode="json")


def _require_skill_registry() -> SkillRegistry:
    if _skill_registry is None:
        raise HTTPException(
            status_code=503, detail="Skill registry not configured"
        )
    return _skill_registry


class SkillCreateRequest(BaseModel):
    name: str
    description: str
    version: str = "1.0.0"
    trigger: dict | None = None
    config: dict | None = None
    tools_required: list[str] | None = None
    agents_granted: list[str] | None = None
    source: str | None = None
    instructions_path: str | None = None
    examples_path: str | None = None


def _skill_from_request(data: dict) -> "Skill":
    # Imported lazily so tests that stub out the registry don't need
    # the pydantic model at import time.
    from gclaw.models.skill import Skill, SkillSource, SkillTrigger, TriggerMode

    trigger_data = data.get("trigger") or {}
    mode_val = trigger_data.get("mode", "manual")
    try:
        trigger_mode = TriggerMode(mode_val)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"invalid trigger.mode {mode_val!r}; "
                f"expected one of {[m.value for m in TriggerMode]}"
            ),
        )
    trigger = SkillTrigger(
        mode=trigger_mode,
        contexts=list(trigger_data.get("contexts") or []),
        command=trigger_data.get("command"),
    )
    source_val = data.get("source") or SkillSource.CUSTOM.value
    try:
        source = SkillSource(source_val)
    except ValueError:
        source = SkillSource.CUSTOM
    return Skill(
        name=data["name"],
        description=data["description"],
        version=data.get("version", "1.0.0"),
        trigger=trigger,
        config=data.get("config") or {},
        tools_required=list(data.get("tools_required") or []),
        agents_granted=list(data.get("agents_granted") or []),
        source=source,
        instructions_path=data.get("instructions_path"),
        examples_path=data.get("examples_path"),
    )


@router.post("/skills")
def create_skill(
    req: SkillCreateRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Create a new skill.

    The skill is persisted in the Firestore skill registry and becomes
    immediately discoverable by agents that either (a) grant it
    explicitly via ``agents_granted`` or (b) include it in their
    per-agent override ``skills`` allowlist.

    Returns 409 when a skill with the same name already exists — use
    PATCH to mutate an existing record.
    """
    from gclaw.models.skill import SkillSource

    registry = _require_skill_registry()
    name = (req.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="skill name is required")
    if not _SKILL_NAME_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail=(
                "skill name must match ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$ "
                "(no slashes, dots, or special chars)"
            ),
        )
    if registry.get(name) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Skill {name!r} already exists — use PATCH",
        )
    payload = req.model_dump()
    payload["name"] = name
    # User-created skills are always CUSTOM. The BUILTIN badge in the
    # UI promises a record that's re-seeded from disk on restart, which
    # isn't true of API-created records — don't let a client spoof it.
    payload["source"] = SkillSource.CUSTOM.value
    skill = _skill_from_request(payload)
    saved = registry.register(skill)
    return saved.model_dump(mode="json")


@router.patch("/skills/{skill_name}")
def patch_skill(
    skill_name: str,
    patch: dict,
    user_id: str = Depends(get_current_user_id),
):
    """Merge a partial update into an existing skill."""
    registry = _require_skill_registry()
    existing = registry.get(skill_name)
    if existing is None:
        raise HTTPException(
            status_code=404, detail=f"Skill {skill_name!r} not found"
        )
    merged = existing.model_dump(mode="json")
    for key, value in (patch or {}).items():
        if key == "name":
            # Renaming requires create+delete; reject here to keep the
            # Firestore doc ID and the skill name in sync.
            if value and value != existing.name:
                raise HTTPException(
                    status_code=400,
                    detail="skill rename is not supported; delete + create instead",
                )
            continue
        if key == "source":
            # Source is the skill's origin — freezing it at create time
            # prevents a client from promoting a CUSTOM record into a
            # BUILTIN badge with misleading "re-seeded on restart" UX.
            continue
        merged[key] = value
    skill = _skill_from_request(merged)
    saved = registry.register(skill)
    return saved.model_dump(mode="json")


@router.delete("/skills/{skill_name}")
def delete_skill(
    skill_name: str,
    user_id: str = Depends(get_current_user_id),
):
    """Remove a skill from the registry.

    Built-in skills shipped in ``skills/<name>/`` are re-seeded from
    disk on the next app restart. To keep a built-in disabled, delete
    its directory or flip a per-agent override allowlist instead.
    """
    registry = _require_skill_registry()
    if registry.get(skill_name) is None:
        raise HTTPException(
            status_code=404, detail=f"Skill {skill_name!r} not found"
        )
    registry.unregister(skill_name)
    return {"status": "deleted", "name": skill_name}


# --- Memory ---


@router.get("/memory/search")
async def search_memories(
    q: str,
    agent_id: str | None = None,
    top_k: int = 20,
    user_id: str = Depends(get_current_user_id),
):
    """Search memories via semantic search."""
    if _memory_service is None:
        raise HTTPException(status_code=503, detail="Memory service not enabled")
    memories = await _memory_service.recall(
        user_id=user_id,
        query=q,
        agent_id=agent_id,
        top_k=top_k,
    )
    return [m.model_dump(mode="json") for m in memories]


@router.get("/memory/list")
async def list_memories(
    agent_id: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    """List all memories for the authenticated user."""
    if _memory_service is None:
        raise HTTPException(status_code=503, detail="Memory service not enabled")
    scope = MemoryScope(user_id=user_id, agent=agent_id)
    memories = await _memory_service._client.list_memories(scope=scope)
    return [m.model_dump(mode="json") for m in memories]


class DeleteMemoryRequest(BaseModel):
    fact: str
    agent_id: str | None = None


@router.post("/memory/delete")
async def delete_memory(
    req: DeleteMemoryRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Delete a specific memory by its fact text."""
    if _memory_service is None:
        raise HTTPException(status_code=503, detail="Memory service not enabled")
    scope = MemoryScope(user_id=user_id, agent=req.agent_id)
    await _memory_service._client.delete_memory(scope=scope, fact=req.fact)
    return {"status": "deleted"}


@router.delete("/memory")
async def wipe_my_memories(
    user_id: str = Depends(get_current_user_id),
):
    """Right-to-delete: wipe every memory for the authenticated user.

    Lists all user-scoped memories and deletes each one. Agent-scoped
    and shared-channel memories are not touched — see
    MemoryService.wipe_user_memories for the limitation rationale.

    Returns the number of memories successfully deleted. The count
    may be lower than the total if some deletes failed (each failure
    is logged).
    """
    if _memory_service is None:
        raise HTTPException(status_code=503, detail="Memory service not enabled")
    deleted = await _memory_service.wipe_user_memories(user_id)
    return {"status": "wiped", "deleted": deleted}


# --- Transports ---


@router.get("/transports")
def list_transports(user_id: str = Depends(get_current_user_id)):
    """List all registered announce transports plus the default."""
    if _cron_delivery_service is None:
        raise HTTPException(
            status_code=503, detail="Cron delivery service not configured"
        )
    return {
        "transports": _cron_delivery_service.list_transports(),
        "default": _cron_delivery_service.default,
    }


# --- Crons ---


@router.get("/crons")
def list_crons_admin(user_id: str = Depends(get_current_user_id)):
    """List all cron schedules with full detail."""
    crons = _cron_service.list_all()
    return [c.model_dump(mode="json") for c in crons]


@router.post("/crons/{cron_id}/toggle")
def toggle_cron(
    cron_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Toggle a cron between active and paused."""
    from gclaw.models.cron import CronStatus

    # Peek at current status by listing all and finding by id
    crons = _cron_service.list_all()
    cron = next((c for c in crons if c.id == cron_id), None)
    if cron is None:
        raise HTTPException(status_code=404, detail=f"Cron '{cron_id}' not found")

    if cron.status == CronStatus.ACTIVE:
        updated = _cron_service.pause(cron_id)
    else:
        updated = _cron_service.resume(cron_id)

    return updated.model_dump(mode="json")
