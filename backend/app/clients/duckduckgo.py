from __future__ import annotations

import html
import ipaddress
import logging
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx


logger = logging.getLogger(__name__)


class DuckDuckGoSearchError(Exception):
    pass


class DuckDuckGoSearchTimeoutError(DuckDuckGoSearchError):
    pass


class DuckDuckGoSearchUnavailableError(DuckDuckGoSearchError):
    pass


class DuckDuckGoSearchBlockedError(DuckDuckGoSearchError):
    pass


@dataclass(slots=True)
class DuckDuckGoSearchResult:
    position: int
    title: str
    url: str
    snippet: str
    page_excerpt: str | None = None


_PRIVATE_IP_KINDS = (
    "is_private",
    "is_loopback",
    "is_link_local",
    "is_reserved",
    "is_multicast",
    "is_unspecified",
)


def _is_public_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False

    return not any(getattr(ip, attr) for attr in _PRIVATE_IP_KINDS)


def is_safe_http_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False

    try:
        resolved = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError:
        return False

    addresses = set()
    for entry in resolved:
        sockaddr = entry[4]
        if not sockaddr:
            continue
        addresses.add(sockaddr[0])

    return bool(addresses) and all(_is_public_ip(address) for address in addresses)


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _clean_text(text: str, limit: int) -> str:
    cleaned = _normalize_whitespace(html.unescape(text))
    return cleaned[:limit]


def _extract_target_url(href: str, base_url: str) -> str:
    absolute = urljoin(base_url, href)
    parsed = urlparse(absolute)
    if parsed.hostname and parsed.hostname.endswith("duckduckgo.com") and parsed.path == "/l/":
        query = parse_qs(parsed.query)
        target = query.get("uddg", [""])[0]
        if target:
            absolute = unquote(target)
    return absolute


class _VisibleTextParser(HTMLParser):
    _skip_tags = {
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "canvas",
        "iframe",
    }
    _block_tags = {
        "article",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "p",
        "section",
        "tr",
        "td",
        "th",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self._parts: list[str] = []
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag in self._skip_tags:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = True
            return
        if tag in self._block_tags:
            self._parts.append("\n")

    def handle_endtag(self, tag: str):
        if tag in self._skip_tags:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
            return
        if tag in self._block_tags:
            self._parts.append("\n")

    def handle_data(self, data: str):
        if self._skip_depth:
            return
        if self._in_title:
            self._title_parts.append(data)
        else:
            self._parts.append(data)

    def get_title(self) -> str:
        return _clean_text("".join(self._title_parts), 240)

    def get_excerpt(self, limit: int = 1200) -> str:
        return _clean_text("".join(self._parts), limit)


def _extract_page_excerpt(html_text: str) -> tuple[str, str]:
    parser = _VisibleTextParser()
    parser.feed(html_text)
    return parser.get_title(), parser.get_excerpt()


def _extract_duckduckgo_results(html_text: str, base_url: str, max_results: int) -> list[DuckDuckGoSearchResult]:
    results: list[DuckDuckGoSearchResult] = []
    title_matches = list(
        re.finditer(
            r'<a[^>]*class="[^"]*\bresult__a\b[^"]*"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
            html_text,
            re.I | re.S,
        )
    )

    for index, match in enumerate(title_matches[:max_results], start=1):
        href = html.unescape(match.group("href"))
        title = _clean_text(re.sub(r"<[^>]+>", " ", match.group("title")), 240)
        if not title:
            continue

        next_start = title_matches[index].start() if index < len(title_matches) else len(html_text)
        block = html_text[match.end() : next_start]
        snippet_match = re.search(
            r'class="[^"]*\bresult__snippet\b[^"]*"[^>]*>(?P<snippet>.*?)</',
            block,
            re.I | re.S,
        )
        snippet = ""
        if snippet_match:
            snippet = _clean_text(re.sub(r"<[^>]+>", " ", snippet_match.group("snippet")), 500)

        url = _extract_target_url(href, base_url)
        results.append(
            DuckDuckGoSearchResult(
                position=index,
                title=title,
                url=url,
                snippet=snippet,
            )
        )

    return results


class DuckDuckGoClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                )
            },
            timeout=httpx.Timeout(15.0, connect=5.0),
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get_text(self, url: str, params: dict[str, str] | None = None) -> str:
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise DuckDuckGoSearchTimeoutError("DuckDuckGo request timed out.") from exc
        except httpx.RequestError as exc:
            raise DuckDuckGoSearchUnavailableError("DuckDuckGo is unavailable.") from exc
        except httpx.HTTPStatusError as exc:
            raise DuckDuckGoSearchUnavailableError("DuckDuckGo returned an error response.") from exc

        return response.text

    async def search(self, query: str, max_results: int = 5) -> list[DuckDuckGoSearchResult]:
        cleaned_query = _normalize_whitespace(query)
        if not cleaned_query:
            return []

        search_html = await self._get_text(
            "https://html.duckduckgo.com/html/",
            params={"q": cleaned_query},
        )
        results = _extract_duckduckgo_results(search_html, "https://html.duckduckgo.com/html/", max_results)

        enriched: list[DuckDuckGoSearchResult] = []
        for result in results:
            try:
                page_excerpt = await self.fetch_page_excerpt(result.url)
            except DuckDuckGoSearchError as exc:
                logger.warning("Skipping page fetch for %s: %s", result.url, exc)
                page_excerpt = None
            enriched.append(
                DuckDuckGoSearchResult(
                    position=result.position,
                    title=result.title,
                    url=result.url,
                    snippet=result.snippet,
                    page_excerpt=page_excerpt,
                )
            )

        return enriched

    async def fetch_page_excerpt(self, url: str) -> str | None:
        if not is_safe_http_url(url):
            return None

        try:
            response = await self._client.get(url)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise DuckDuckGoSearchTimeoutError("Page fetch timed out.") from exc
        except httpx.RequestError as exc:
            raise DuckDuckGoSearchUnavailableError("Page fetch failed.") from exc
        except httpx.HTTPStatusError:
            return None

        final_url = str(response.url)
        if not is_safe_http_url(final_url):
            return None

        title, excerpt = _extract_page_excerpt(response.text)
        parts = [part for part in (title, excerpt) if part]
        if not parts:
            return None
        return _clean_text("\n".join(parts), 1200)


def serialize_search_results(results: list[DuckDuckGoSearchResult]) -> list[dict]:
    return [
        {
            "position": result.position,
            "title": result.title,
            "url": result.url,
            "snippet": result.snippet,
            "page_excerpt": result.page_excerpt,
        }
        for result in results
    ]
