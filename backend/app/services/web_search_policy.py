from __future__ import annotations

from dataclasses import dataclass
import re

from app.models.chat import ChatTurnRequest, WebSearchMode


WebSearchReasonCode = str


@dataclass(slots=True)
class WebSearchDecision:
    should_search: bool
    reason_code: WebSearchReasonCode
    mode: WebSearchMode
    confidence: float


_URL_RE = re.compile(r"https?://\S+|\bwww\.\S+", re.IGNORECASE)

_EXPLICIT_SEARCH_PATTERNS = (
    r"\bsearch the web\b",
    r"\bsearch web\b",
    r"\bsearch online\b",
    r"\blook this up\b",
    r"\blook it up\b",
    r"\bfind current information\b",
    r"\bverify online\b",
    r"\bbrowse the web\b",
    r"\bcheck online\b",
    r"\blook online\b",
    r"\buse the web\b",
    r"\bпоищи(?:\s+в\s+интернете)?\b",
    r"\bнайди(?:\s+в\s+интернете)?\b",
    r"\bпосмотри(?:\s+в\s+интернете)?\b",
    r"\bпроверь(?:\s+онлайн|\s+в\s+интернете)?\b",
    r"\bпоиск(?:\s+в\s+интернете)?\b",
    r"\bоткрой\s+ссылку\b",
)

_CURRENT_INFORMATION_PATTERNS = (
    r"\blatest\b",
    r"\bcurrent\b",
    r"\brecent\b",
    r"\bnow\b",
    r"\btoday\b",
    r"\bup[- ]?to[- ]?date\b",
    r"\bas of\b",
    r"\bfresh\b",
    r"\bпоследн(?:ие|яя|ее|ий)\b",
    r"\bактуальн\w*\b",
    r"\bсвеж\w*\b",
    r"\bсейчас\b",
    r"\bсегодня\b",
    r"\bна\s+сегодня\b",
    r"\bпо\s+состоянию\s+на\b",
    r"\bновост\w*\b",
)

_DYNAMIC_TOPIC_PATTERNS = (
    r"\bnews\b",
    r"\bweather\b",
    r"\bsports?\b",
    r"\bscore\b",
    r"\bstandings\b",
    r"\bstocks?\b",
    r"\bshare price\b",
    r"\bstock price\b",
    r"\bcrypto\b",
    r"\bbitcoin\b",
    r"\bether(?:ium)?\b",
    r"\bexchange rate\b",
    r"\bcurrency\b",
    r"\bschedule\b",
    r"\bflight\b",
    r"\btrain\b",
    r"\bversion\b",
    r"\brelease\b",
    r"\belection\b",
    r"\bresults?\b",
    r"\bновост\w*\b",
    r"\bпогод\w*\b",
    r"\bспорт\w*\b",
    r"\bсчет\w*\b",
    r"\bтаблиц\w*\b",
    r"\bкурс\w*\b",
    r"\bвалют\w*\b",
    r"\bрасписан\w*\b",
    r"\bверси\w*\b",
    r"\bрелиз\w*\b",
    r"\bвыбор\w*\b",
    r"\bрезультат\w*\b",
    r"\bбиткоин\b",
    r"\bэфириум\b",
    r"\bкрипто\w*\b",
)


def _normalize_query(query: str) -> str:
    return " ".join(query.split()).strip()


def _matches_any(patterns: tuple[str, ...], text: str) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _has_url(text: str) -> bool:
    return bool(_URL_RE.search(text))


def _resolve_mode(payload: ChatTurnRequest) -> tuple[WebSearchMode, str]:
    if "web_search_mode" in payload.model_fields_set:
        return payload.web_search_mode, "explicit_mode"

    if "use_web_search" in payload.model_fields_set and payload.use_web_search is not None:
        return ("always" if payload.use_web_search else "off"), "legacy_flag"

    return "off", "default_mode"


def decide_web_search(payload: ChatTurnRequest) -> WebSearchDecision:
    mode, source = _resolve_mode(payload)
    query = _normalize_query(payload.content)
    lowered = query.lower()

    if mode == "off":
        reason_code = "mode_off" if source != "legacy_flag" else "forced_off"
        confidence = 1.0
        return WebSearchDecision(False, reason_code, mode, confidence)

    if mode == "always":
        reason_code = "mode_always" if source == "explicit_mode" else "forced_on"
        confidence = 1.0
        return WebSearchDecision(True, reason_code, mode, confidence)

    if _has_url(query):
        return WebSearchDecision(True, "url_lookup", mode, 0.95)

    if _matches_any(_EXPLICIT_SEARCH_PATTERNS, lowered):
        return WebSearchDecision(True, "explicit_search_request", mode, 0.95)

    if _matches_any(_CURRENT_INFORMATION_PATTERNS, lowered):
        return WebSearchDecision(True, "current_information", mode, 0.8)

    if _matches_any(_DYNAMIC_TOPIC_PATTERNS, lowered):
        return WebSearchDecision(True, "dynamic_topic", mode, 0.7)

    return WebSearchDecision(False, "no_search_signal", mode, 0.2)
