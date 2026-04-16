"""Image generation tools for GClaw agents.

Wraps the Gemini 3 Pro Image API (aka Nano Banana Pro) as agent-callable
tool functions. Content agents chain this with postiz_upload_image to
create LinkedIn posts with images.

The GEMINI_API_KEY env var (bootstrapped from watson-gemini-api-key at
startup) is used for auth. If unavailable, tools return an error string.
"""

from __future__ import annotations

import base64
import logging
import os
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

logger = logging.getLogger(__name__)

_TMP_DIR = Path("/tmp/gclaw-images")


async def generate_image(
    prompt: str,
    filename: str = "",
    resolution: str = "2K",
) -> str:
    """Generate an image using Gemini 3 Pro Image (Nano Banana Pro).

    Args:
        prompt: Image description. Follow the nano-banana-pro skill
            guidelines (clean backgrounds, no holographic, 4:5 ratio).
        filename: Output filename (without directory). Auto-generated
            if empty. Saved under /tmp/gclaw-images/.
        resolution: "1K", "2K" (default), or "4K".

    Returns:
        Path to the saved PNG file on success, or an error string.
        Chain with postiz_upload_image(path) to upload to Postiz.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "generate_image failed: GEMINI_API_KEY not set. Bootstrap watson-gemini-api-key first."

    if not prompt.strip():
        return "generate_image failed: prompt is empty."

    if resolution not in ("1K", "2K", "4K"):
        resolution = "2K"

    if not filename:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        filename = f"{ts}-{uuid.uuid4().hex[:8]}.png"
    if not filename.endswith(".png"):
        filename += ".png"

    _TMP_DIR.mkdir(parents=True, exist_ok=True)
    output_path = _TMP_DIR / filename

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-3-pro-image-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                image_config=types.ImageConfig(image_size=resolution),
            ),
        )

        image_saved = False
        model_text = ""
        for part in response.parts:
            if part.text is not None:
                model_text = part.text
            elif part.inline_data is not None:
                from PIL import Image as PILImage

                image_data = part.inline_data.data
                if isinstance(image_data, str):
                    image_data = base64.b64decode(image_data)

                image = PILImage.open(BytesIO(image_data))
                if image.mode == "RGBA":
                    rgb = PILImage.new("RGB", image.size, (255, 255, 255))
                    rgb.paste(image, mask=image.split()[3])
                    rgb.save(str(output_path), "PNG")
                elif image.mode == "RGB":
                    image.save(str(output_path), "PNG")
                else:
                    image.convert("RGB").save(str(output_path), "PNG")
                image_saved = True

        if not image_saved:
            detail = f" Model said: {model_text}" if model_text else ""
            return f"generate_image failed: no image in response.{detail}"

        logger.info(
            "generate_image: saved %s (%d bytes, resolution=%s)",
            output_path,
            output_path.stat().st_size,
            resolution,
        )
        return str(output_path)

    except Exception as exc:
        logger.warning("generate_image failed: %s", exc, exc_info=True)
        return f"generate_image failed: {exc}"


async def generate_image_b64(
    prompt: str,
    resolution: str = "2K",
) -> str:
    """Generate an image and return it as a base64 string.

    Useful when the agent wants to pass the image directly to
    postiz_upload_image_b64 or context_write_image without touching
    the filesystem.

    Returns:
        Base64-encoded PNG string on success, or an error string
        (starts with "generate_image_b64 failed:").
    """
    path = await generate_image(prompt, resolution=resolution)
    if path.startswith("generate_image failed:"):
        return path.replace("generate_image failed:", "generate_image_b64 failed:", 1)
    try:
        data = Path(path).read_bytes()
        return base64.b64encode(data).decode("ascii")
    except Exception as exc:
        return f"generate_image_b64 failed: {exc}"
