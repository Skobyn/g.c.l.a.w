"""Research tool functions — web search stub and HTTP fetch."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


async def web_search(query: str) -> str:
    """Search the web for information.

    Args:
        query: the search query string.

    Returns:
        Search results summary.
    """
    logger.info("web_search stub called with query: %s", query)
    return (
        f"[web_search is a stub placeholder for query: '{query}']\n"
        "A real web search backend (Serper/Brave/Google CSE) is not yet "
        "integrated. Follow-up spec will wire this up."
    )


async def fetch_url(url: str, max_chars: int = 4000) -> str:
    """Fetch the text content of a URL."""
    try:
        async with httpx.AsyncClient(
            timeout=15.0, follow_redirects=True
        ) as client:
            response = await client.get(url)
    except Exception as e:
        logger.warning("fetch_url %s failed: %s", url, e)
        return f"Fetch failed: {e}"

    text = response.text if hasattr(response, "text") else str(response)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (truncated)"
    return text
