"""Research tool functions — Gemini-grounded web search and HTTP fetch.

``web_search`` uses Gemini's built-in Google Search grounding tool.
The tool returns a synthesized answer plus the source citations, so
the calling agent can relay them without a second round-trip. No
extra API key is required beyond the existing Gemini/Vertex ADC the
app already uses.

``fetch_url`` is a plain-text fetcher for a specific URL — useful
when the agent already knows where to look.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


# Grounding is only supported on 2.x+ models. Flash keeps search fast
# and cheap; callers can override via the WEB_SEARCH_MODEL env var if
# they want a beefier synthesizer.
_DEFAULT_SEARCH_MODEL = os.environ.get("WEB_SEARCH_MODEL", "gemini-2.5-flash")
_MAX_QUERY_CHARS = 1000
_MAX_RESULT_CHARS = 4000


async def web_search(query: str) -> str:
    """Search the web and return a synthesized answer with sources.

    Uses Gemini's Google Search grounding: the model formulates search
    queries, reads the returned snippets, and produces an answer with
    inline citations. We reformat the citations into a compact source
    list the caller can pass through verbatim.

    Args:
        query: Plain-language question or search string.

    Returns:
        Multi-line string: synthesized answer, blank line, then
        ``Sources:`` with URLs. If grounding is unavailable the
        function returns a best-effort non-grounded answer and a note.
    """
    if not query or not query.strip():
        return "web_search: empty query."
    q = query.strip()
    if len(q) > _MAX_QUERY_CHARS:
        q = q[:_MAX_QUERY_CHARS]

    try:
        from google import genai
        from google.genai import types
    except Exception as e:  # pragma: no cover — package missing
        logger.warning("web_search: google-genai unavailable: %s", e)
        return (
            f"web_search error: google-genai is not installed "
            f"({e}). Install google-adk[extensions] or google-genai."
        )

    # Prefer Vertex when the app is already configured for it (matches
    # the rest of the codebase — voice session, catalog tests, etc.).
    use_vertex = _use_vertex()

    try:
        if use_vertex:
            client = genai.Client(
                vertexai=True,
                project=os.environ.get("GCP_PROJECT_ID"),
                location=os.environ.get("GCP_LOCATION", "us-central1"),
            )
        else:
            client = genai.Client()
    except Exception as e:
        logger.warning("web_search: genai client init failed: %s", e)
        return f"web_search error: client init failed ({e})."

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )

    try:
        response = await client.aio.models.generate_content(
            model=_DEFAULT_SEARCH_MODEL,
            contents=q,
            config=config,
        )
    except Exception as e:
        logger.warning("web_search: generate_content failed: %s", e)
        return f"web_search error: {e}"

    answer = (getattr(response, "text", None) or "").strip()
    sources = _extract_sources(response)

    if len(answer) > _MAX_RESULT_CHARS:
        answer = answer[:_MAX_RESULT_CHARS] + "\n… (truncated)"

    if not answer:
        return "web_search: no answer produced."

    if not sources:
        return answer

    src_block = "\n".join(
        f"- {s['title'] or s['url']}: {s['url']}" for s in sources[:10]
    )
    return f"{answer}\n\nSources:\n{src_block}"


def _use_vertex() -> bool:
    """Choose backend: Vertex if the env says so or we have a project."""
    explicit = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower()
    if explicit in ("true", "1", "yes"):
        return True
    if explicit in ("false", "0", "no"):
        return False
    # Default: Vertex when a GCP project is set and no Gemini API key
    # is around. Matches how the rest of the app authenticates.
    has_project = bool(os.environ.get("GCP_PROJECT_ID"))
    has_api_key = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    return has_project and not has_api_key


def _extract_sources(response) -> list[dict]:
    """Pull {title, url} tuples out of grounding_metadata.

    The Gemini response shape for grounded calls:
      response.candidates[0].grounding_metadata.grounding_chunks[i].web.{uri,title}
    """
    out: list[dict] = []
    try:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return out
        meta = getattr(candidates[0], "grounding_metadata", None)
        if meta is None:
            return out
        chunks = getattr(meta, "grounding_chunks", None) or []
        for ch in chunks:
            web = getattr(ch, "web", None)
            if web is None:
                continue
            uri = getattr(web, "uri", None) or ""
            title = getattr(web, "title", None) or ""
            if uri:
                out.append({"url": uri, "title": title})
    except Exception:
        # Never break the caller on citation parsing — return what we have.
        logger.debug("web_search: source extraction failed", exc_info=True)
    return out


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
