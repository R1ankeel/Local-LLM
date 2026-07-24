from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from app.core.config import XAI_API_KEY, XAI_MODEL, XAI_TIMEOUT_SECONDS


logger = logging.getLogger(__name__)


class XAIWebSearchError(Exception):
    pass


class XAIWebSearchConfigError(XAIWebSearchError):
    pass


class XAIWebSearchTimeoutError(XAIWebSearchError):
    pass


class XAIWebSearchUnavailableError(XAIWebSearchError):
    pass


class XAIWebSearchAuthError(XAIWebSearchError):
    pass


class XAIWebSearchRateLimitError(XAIWebSearchError):
    pass


@dataclass(slots=True)
class XAIWebSearchResult:
    position: int
    title: str
    url: str
    snippet: str
    page_excerpt: str | None = None


_XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"


def _normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url.strip()
    return urlunparse(parsed._replace(fragment=""))


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for url in urls:
        normalized = _normalize_url(url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _title_from_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname:
        host = parsed.hostname.removeprefix("www.")
        return host
    return url


def _extract_output_text(data: dict[str, Any]) -> str:
    texts: list[str] = []
    for item in data.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict) or content.get("type") != "output_text":
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())

    if not texts:
        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            texts.append(output_text.strip())

    return "\n\n".join(texts).strip()


def _collect_url_metadata(data: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    urls: list[str] = []
    titles: dict[str, str] = {}

    citations = data.get("citations", [])
    if isinstance(citations, list):
        for citation in citations:
            if isinstance(citation, str):
                urls.append(citation)
            elif isinstance(citation, dict):
                url = citation.get("url")
                if isinstance(url, str):
                    urls.append(url)
                    title = citation.get("title")
                    if isinstance(title, str) and title.strip():
                        titles[_normalize_url(url)] = title.strip()

    for item in data.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict) or content.get("type") != "output_text":
                continue
            for annotation in content.get("annotations", []):
                if not isinstance(annotation, dict):
                    continue
                url = annotation.get("url")
                if not isinstance(url, str):
                    continue
                urls.append(url)
                title = annotation.get("title")
                if isinstance(title, str) and title.strip():
                    titles[_normalize_url(url)] = title.strip()

    return urls, titles


class XAIWebSearchClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else XAI_API_KEY
        self._model = model if model is not None else XAI_MODEL
        self._timeout_seconds = timeout_seconds if timeout_seconds is not None else XAI_TIMEOUT_SECONDS
        self._client = httpx.AsyncClient(
            base_url="https://api.x.ai/v1",
            headers={
                "Authorization": f"Bearer {self._api_key}" if self._api_key else "",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(self._timeout_seconds, connect=5.0),
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _ensure_configured(self) -> None:
        if not self._api_key:
            raise XAIWebSearchConfigError("XAI_API_KEY is required for xAI web search.")
        if not self._model:
            raise XAIWebSearchConfigError("XAI_MODEL is required for xAI web search.")

    async def search(self, query: str, max_results: int = 5) -> list[XAIWebSearchResult]:
        self._ensure_configured()
        cleaned_query = " ".join(query.split()).strip()
        if not cleaned_query:
            return []

        payload = {
            "model": self._model,
            "input": [
                {
                    "role": "user",
                    "content": cleaned_query,
                },
            ],
            "tools": [
                {
                    "type": "web_search",
                },
            ],
            "include": ["no_inline_citations"],
            "store": False,
        }

        try:
            response = await self._client.post(_XAI_RESPONSES_URL, json=payload)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise XAIWebSearchTimeoutError("xAI request timed out.") from exc
        except httpx.RequestError as exc:
            raise XAIWebSearchUnavailableError("xAI is unavailable.") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in {401, 403}:
                raise XAIWebSearchAuthError("xAI rejected the API key.") from exc
            if status == 429:
                raise XAIWebSearchRateLimitError("xAI rate limit exceeded.") from exc
            raise XAIWebSearchUnavailableError("xAI returned an error response.") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise XAIWebSearchUnavailableError("xAI returned invalid JSON.") from exc

        output_text = _extract_output_text(data)
        urls, titles = _collect_url_metadata(data)
        ordered_urls = _dedupe_urls(urls)

        if not ordered_urls:
            raise XAIWebSearchError("xAI web search returned no citations.")

        if not output_text:
            output_text = cleaned_query

        excerpt = output_text[:1200]
        snippet = output_text[:500] or cleaned_query

        results: list[XAIWebSearchResult] = []
        for position, url in enumerate(ordered_urls[:max_results], start=1):
            normalized_url = _normalize_url(url)
            results.append(
                XAIWebSearchResult(
                    position=position,
                    title=titles.get(normalized_url) or _title_from_url(normalized_url),
                    url=normalized_url,
                    snippet=snippet[:4000],
                    page_excerpt=excerpt or None,
                )
            )

        logger.debug("xAI web search returned %d citations", len(results))
        return results
