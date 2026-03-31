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
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gclaw.auth.dependencies import get_current_user_id
from gclaw.config.loader import ConfigLoader
from gclaw.heartbeat.log import HeartbeatLogRepo
from gclaw.memory.service import MemoryService
from gclaw.models.memory import MemoryScope
from gclaw.skill.registry import SkillRegistry
from gclaw.cron.service import CronService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")

_config_loader: ConfigLoader | None = None
_hb_repo_factory: Callable[[str], HeartbeatLogRepo] | None = None
_skill_registry: SkillRegistry | None = None
_memory_service: MemoryService | None = None
_cron_service: CronService | None = None


def init_admin_router(
    config_loader: ConfigLoader,
    heartbeat_log_repo_factory: Callable[[str], HeartbeatLogRepo],
    skill_registry: SkillRegistry,
    memory_service: MemoryService,
    cron_service: CronService,
) -> APIRouter:
    global _config_loader, _hb_repo_factory, _skill_registry
    global _memory_service, _cron_service
    _config_loader = config_loader
    _hb_repo_factory = heartbeat_log_repo_factory
    _skill_registry = skill_registry
    _memory_service = memory_service
    _cron_service = cron_service
    return router


# --- Agents ---


class AgentInfo(BaseModel):
    name: str
    has_soul_overlay: bool


@router.get("/agents")
def list_agents(user_id: str = Depends(get_current_user_id)):
    """List all configured agents with basic info."""
    agents_dir = os.path.join(_config_loader._config_dir, "agents")
    result = []
    if os.path.isdir(agents_dir):
        for fname in sorted(os.listdir(agents_dir)):
            if fname.endswith(".md"):
                agent_name = fname.removesuffix(".md")
                # Check for soul overlay matching the first segment of the agent name
                soul_dir = os.path.join(_config_loader._config_dir, "soul")
                has_overlay = os.path.isfile(
                    os.path.join(soul_dir, f"{agent_name.split('-')[0]}.md")
                )
                result.append({
                    "name": agent_name,
                    "has_soul_overlay": has_overlay,
                })
    return result


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


# --- Soul Files ---


@router.get("/soul/{name}")
def get_soul_file(
    name: str,
    user_id: str = Depends(get_current_user_id),
):
    """Read a soul file by name (e.g., 'base', 'workspace')."""
    try:
        content = _config_loader.load_soul(name)
        return {"name": name, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Soul file '{name}' not found")


class SoulUpdateRequest(BaseModel):
    content: str


@router.put("/soul/{name}")
def update_soul_file(
    name: str,
    req: SoulUpdateRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Update a soul file's content."""
    soul_path = os.path.join(_config_loader._config_dir, "soul", f"{name}.md")
    if not os.path.isfile(soul_path):
        raise HTTPException(status_code=404, detail=f"Soul file '{name}' not found")
    with open(soul_path, "w") as f:
        f.write(req.content)
    return {"name": name, "status": "updated"}


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


# --- Memory ---


@router.get("/memory/search")
async def search_memories(
    q: str,
    agent_id: str | None = None,
    top_k: int = 20,
    user_id: str = Depends(get_current_user_id),
):
    """Search memories via semantic search."""
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
    scope = MemoryScope(user_id=user_id, agent=req.agent_id)
    await _memory_service._client.delete_memory(scope=scope, fact=req.fact)
    return {"status": "deleted"}


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
