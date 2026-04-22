"""Postiz social media scheduling tools.

Upload images, create draft posts, and register images with the reviewer
app.  All tool functions return strings and never raise (ADK-safe).

Module-level config is set once at app startup via ``set_postiz_config``.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone

import httpx

from gclaw.tools.catalog.builtin_registry import tool_export

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level config holder (set at startup by main.py)
# ---------------------------------------------------------------------------

_config: dict = {}

_TIMEOUT = 15.0  # seconds


def set_postiz_config(
    *,
    base_url: str,
    reviewer_url: str,
    api_token: str,
    channel_primary: str,
    channel_secondary: str,
) -> None:
    """Inject runtime configuration. Called once from ``main.py``."""
    global _config
    _config = {
        "base_url": base_url.rstrip("/"),
        "reviewer_url": reviewer_url.rstrip("/"),
        "api_token": api_token,
        "channel_primary": channel_primary,
        "channel_secondary": channel_secondary,
    }


def _err(verb: str, exc: Exception) -> str:
    logger.warning("postiz %s failed: %s", verb, exc)
    return f"Postiz {verb} failed: {exc}"


def _require_config() -> dict:
    if not _config or not _config.get("api_token"):
        raise RuntimeError("Postiz tools not configured (missing API token)")
    return _config


def _auth_headers(token: str) -> dict[str, str]:
    """Return auth headers.  Postiz uses a bare token, no Bearer prefix."""
    return {"Authorization": token}


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


@tool_export(description="Upload an image file to Postiz.")
async def postiz_upload_image(image_path: str) -> str:
    """Upload an image file to Postiz.

    Args:
        image_path: Local filesystem path to the image (e.g. /tmp/foo.png).

    Returns:
        ``"Uploaded: id=<id> path=<url>"`` on success, or an error string.
    """
    try:
        cfg = _require_config()
    except Exception as e:
        return _err("upload_image", e)

    if not os.path.isfile(image_path):
        return f"Postiz upload_image failed: file not found: {image_path}"

    try:
        filename = os.path.basename(image_path)
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            with open(image_path, "rb") as f:
                resp = await client.post(
                    f"{cfg['base_url']}/api/public/v1/upload",
                    headers=_auth_headers(cfg["api_token"]),
                    files={"file": (filename, f)},
                )
        if resp.status_code >= 400:
            return f"Postiz upload_image failed: HTTP {resp.status_code} — {resp.text[:200]}"
        data = resp.json()
        return f"Uploaded: id={data['id']} path={data['path']}"
    except Exception as e:
        return _err("upload_image", e)


@tool_export(description="Upload a base64-encoded image to Postiz.")
async def postiz_upload_image_b64(
    image_base64: str,
    filename: str = "image.png",
) -> str:
    """Upload a base64-encoded image to Postiz.

    Decodes the image, writes it to a temp file, and delegates to
    ``postiz_upload_image``.

    Args:
        image_base64: Base64-encoded image data.
        filename: Desired filename (used in the upload).

    Returns:
        Upload result string from ``postiz_upload_image``.
    """
    try:
        data = base64.b64decode(image_base64, validate=True)
    except Exception as e:
        return _err("upload_image_b64", e)

    tmp_path = os.path.join(tempfile.gettempdir(), filename)
    try:
        with open(tmp_path, "wb") as f:
            f.write(data)
        return await postiz_upload_image(tmp_path)
    except Exception as e:
        return _err("upload_image_b64", e)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@tool_export(description="Create a draft post in Postiz with optional images and a publish date.")
async def postiz_create_draft(
    content: str,
    image_ids_json: str = "[]",
    channel_id: str = "",
    date: str = "",
) -> str:
    """Create a draft post in Postiz.

    Args:
        content: The post text body.
        image_ids_json: JSON array of ``[{"id": "...", "path": "..."}]``
            objects from prior upload responses.
        channel_id: Postiz integration/channel ID.  Defaults to
            ``channel_primary`` from config when empty.
        date: ISO-format publish date.  Defaults to now + 1 day.

    Returns:
        ``"Draft created: postId=<id>"`` on success, or an error string.
    """
    try:
        cfg = _require_config()
    except Exception as e:
        return _err("create_draft", e)

    try:
        images = json.loads(image_ids_json) if image_ids_json else []
    except json.JSONDecodeError as e:
        return _err("create_draft", e)

    effective_channel = channel_id or cfg.get("channel_primary", "")
    if not effective_channel:
        return "Postiz create_draft failed: no channel_id provided and no default configured"

    if not date:
        date = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    payload = {
        "type": "draft",
        "date": date,
        "shortLink": False,
        "tags": [],
        "posts": [
            {
                "integration": {"id": effective_channel},
                "value": [
                    {
                        "content": content,
                        "image": images,
                    }
                ],
            }
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{cfg['base_url']}/api/public/v1/posts",
                headers={
                    **_auth_headers(cfg["api_token"]),
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code >= 400:
            return f"Postiz create_draft failed: HTTP {resp.status_code} — {resp.text[:200]}"
        data = resp.json()
        # Response is an array: [{"postId": "...", "integration": "..."}]
        if isinstance(data, list) and data:
            post_id = data[0].get("postId", "unknown")
        elif isinstance(data, dict):
            post_id = data.get("postId", "unknown")
        else:
            post_id = "unknown"
        return f"Draft created: postId={post_id}"
    except Exception as e:
        return _err("create_draft", e)


@tool_export(description="Register image URLs with the Postiz reviewer app after creating a post.")
async def postiz_register_images(
    post_id: str,
    image_urls_json: str,
) -> str:
    """Register image URLs with the Postiz reviewer app.

    Must be called after creating a post so images appear in the reviewer.

    Args:
        post_id: The Postiz post ID from the create_draft response.
        image_urls_json: JSON array of image URL strings.

    Returns:
        Confirmation string or an error message.
    """
    try:
        cfg = _require_config()
    except Exception as e:
        return _err("register_images", e)

    try:
        urls = json.loads(image_urls_json) if image_urls_json else []
    except json.JSONDecodeError as e:
        return _err("register_images", e)

    payload = {"postId": post_id, "images": urls}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{cfg['reviewer_url']}/api/image-cache",
                headers={"Content-Type": "application/json"},
                json=payload,
            )
        if resp.status_code >= 400:
            return f"Postiz register_images failed: HTTP {resp.status_code} — {resp.text[:200]}"
        return f"Images registered for post {post_id}"
    except Exception as e:
        return _err("register_images", e)


@tool_export(description="List available Postiz integration channels (IDs + provider).")
async def postiz_list_channels() -> str:
    """List available Postiz integration channels.

    Returns:
        Newline-separated list of channels with IDs, or an error string.
    """
    try:
        cfg = _require_config()
    except Exception as e:
        return _err("list_channels", e)

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{cfg['base_url']}/api/public/v1/integrations",
                headers=_auth_headers(cfg["api_token"]),
            )
        if resp.status_code >= 400:
            return f"Postiz list_channels failed: HTTP {resp.status_code} — {resp.text[:200]}"
        data = resp.json()
        if not data:
            return "No Postiz channels found."
        lines = []
        for ch in data:
            name = ch.get("name") or ch.get("identifier") or "unnamed"
            ch_id = ch.get("id", "?")
            provider = ch.get("providerIdentifier") or ch.get("provider") or ""
            lines.append(f"- {name} (id={ch_id}) [{provider}]")
        return "\n".join(lines)
    except Exception as e:
        return _err("list_channels", e)
