from __future__ import annotations

from collections.abc import Sequence

from app.clients.ollama import OllamaClient
from app.core.prompts import CONTEXT_SUMMARY_SYSTEM_PROMPT
from app.models.chat import Message


SUMMARY_BATCH_SIZE = 20


def _format_summary_source(existing_summary: str | None, messages: Sequence[Message]) -> str:
    lines: list[str] = []
    if existing_summary and existing_summary.strip():
        lines.extend(["Current summary:", existing_summary.strip(), ""])
    else:
        lines.append("Current summary: <empty>")
        lines.append("")

    lines.append("Messages to fold in:")
    for message in messages:
        lines.append(f"{message.role}: {message.content}")

    return "\n".join(lines)


def _normalize_summary_text(text: str) -> str:
    return text.strip()


def _summary_update_messages(existing_summary: str | None, messages: Sequence[Message]) -> list[dict]:
    return [
        {"role": "system", "content": CONTEXT_SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": _format_summary_source(existing_summary, messages)},
    ]


async def generate_context_summary(
    client: OllamaClient,
    model: str,
    existing_summary: str | None,
    messages: Sequence[Message],
) -> str:
    request_messages = _summary_update_messages(existing_summary, messages)
    async with client.stream_chat(model, request_messages, False) as response:
        chunks: list[str] = []
        async for chunk in client.iter_content(response):
            chunks.append(chunk)

    summary = _normalize_summary_text("".join(chunks))
    if not summary:
        raise ValueError("Empty context summary response")
    return summary
