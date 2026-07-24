from __future__ import annotations

import json
import logging
from collections.abc import Sequence

from sqlmodel import Session, select

from app.clients.ollama import OllamaClient
from app.core.prompts import MEMORY_CANDIDATE_ANALYSIS_SYSTEM_PROMPT
from app.core.time import utc_now
from app.models.chat import Chat, Message
from app.models.memory import MemoryCandidate, MemoryCandidateRead, MemoryItem
from app.services.memories import list_memories


logger = logging.getLogger(__name__)

MEMORY_CANDIDATE_MAX_COUNT = 5
MEMORY_CANDIDATE_CONTEXT_LIMIT = 24


def list_memory_candidates(
    db: Session,
    user_id: int,
    chat_id: int | None = None,
    status: str = "pending",
) -> list[MemoryCandidate]:
    statement = select(MemoryCandidate).where(MemoryCandidate.user_id == user_id)
    if chat_id is not None:
        statement = statement.where(MemoryCandidate.chat_id == chat_id)
    if status != "all":
        statement = statement.where(MemoryCandidate.status == status)

    return db.exec(
        statement.order_by(
            MemoryCandidate.updated_at.desc(),
            MemoryCandidate.created_at.desc(),
            MemoryCandidate.id.desc(),
        )
    ).all()


def get_memory_candidate(
    db: Session,
    candidate_id: int,
    user_id: int,
    chat_id: int | None = None,
) -> MemoryCandidate | None:
    candidate = db.get(MemoryCandidate, candidate_id)
    if candidate is None or candidate.user_id != user_id:
        return None
    if chat_id is not None and candidate.chat_id != chat_id:
        return None
    return candidate


def _normalize_candidate_content(content: str) -> str:
    return " ".join(content.split()).strip()[:500]


def _candidate_to_read(candidate: MemoryCandidate) -> MemoryCandidateRead:
    return MemoryCandidateRead.model_validate(candidate)


def create_memory_candidate(
    db: Session,
    user_id: int,
    chat_id: int,
    content: str,
    status: str = "pending",
) -> MemoryCandidate:
    candidate = MemoryCandidate(
        user_id=user_id,
        chat_id=chat_id,
        content=_normalize_candidate_content(content),
        status=status,
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


def update_memory_candidate(
    db: Session,
    candidate: MemoryCandidate,
    *,
    status: str | None = None,
) -> tuple[MemoryCandidate, MemoryItem | None]:
    created_memory: MemoryItem | None = None
    changed = False

    if status is not None and candidate.status != status:
        candidate.status = status
        changed = True

    if candidate.status == "accepted":
        existing_memory = db.exec(
            select(MemoryItem)
            .where(MemoryItem.user_id == candidate.user_id)
            .where(MemoryItem.content == candidate.content)
        ).first()
        if existing_memory is None:
            created_memory = MemoryItem(
                user_id=candidate.user_id,
                content=candidate.content,
                is_active=True,
            )
            db.add(created_memory)
            changed = True

    if changed:
        candidate.updated_at = utc_now()
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        if created_memory is not None:
            db.refresh(created_memory)

    return candidate, created_memory


def delete_memory_candidate(db: Session, candidate: MemoryCandidate) -> None:
    db.delete(candidate)
    db.commit()


def _trim_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    if lines and lines[0].strip().lower() == "json":
        lines = lines[1:]
    return "\n".join(lines).strip()


def _candidate_source_text(
    chat: Chat,
    messages: Sequence[Message],
    memories: Sequence[MemoryItem],
    existing_candidates: Sequence[MemoryCandidate],
) -> str:
    lines: list[str] = [
        "Chat metadata:",
        f"chat_id: {chat.id}",
        f"title: {chat.title}",
    ]

    if chat.context_summary and chat.context_summary.strip():
        lines.extend(["", "Conversation summary:", chat.context_summary.strip()])

    lines.extend(["", "Recent conversation:"])
    for message in messages[-MEMORY_CANDIDATE_CONTEXT_LIMIT:]:
        lines.append(f"{message.role}: {message.content}")

    active_memories = [memory.content.strip() for memory in memories if memory.is_active and memory.content.strip()]
    if active_memories:
        lines.extend(["", "Active long-term memories:"])
        for memory in active_memories:
            lines.append(f"- {memory}")

    if existing_candidates:
        lines.extend(["", "Already suggested candidates:"])
        for candidate in existing_candidates:
            lines.append(f"- [{candidate.status}] {candidate.content.strip()}")

    lines.extend(
        [
            "",
            "Return up to 5 new candidate memories as JSON only.",
            "Each item must be a concise, durable fact about the user.",
        ]
    )
    return "\n".join(lines)


def _parse_candidate_response(text: str) -> list[str]:
    cleaned = _trim_code_fence(text)
    if not cleaned:
        return []

    payload = json.loads(cleaned)
    if isinstance(payload, dict):
        items = payload.get("candidates", [])
    else:
        items = payload

    if not isinstance(items, list):
        return []

    contents: list[str] = []
    for item in items[:MEMORY_CANDIDATE_MAX_COUNT]:
        if isinstance(item, str):
            content = _normalize_candidate_content(item)
        elif isinstance(item, dict):
            raw_content = item.get("content") or item.get("text") or item.get("memory")
            if not isinstance(raw_content, str):
                continue
            content = _normalize_candidate_content(raw_content)
        else:
            continue

        if content:
            contents.append(content)

    return contents


async def generate_memory_candidate_contents(
    client: OllamaClient,
    model: str,
    chat: Chat,
    messages: Sequence[Message],
    memories: Sequence[MemoryItem],
    existing_candidates: Sequence[MemoryCandidate],
) -> list[str]:
    request_messages = [
        {"role": "system", "content": MEMORY_CANDIDATE_ANALYSIS_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _candidate_source_text(chat, messages, memories, existing_candidates),
        },
    ]

    async with client.stream_chat(model, request_messages, False) as response:
        chunks: list[str] = []
        async for line in response.aiter_lines():
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping invalid Ollama line while analyzing memory candidates: %s", line)
                continue

            content = payload.get("message", {}).get("content")
            if content:
                chunks.append(content)

            if payload.get("done"):
                break

    return _parse_candidate_response("".join(chunks))


def upsert_memory_candidates(
    db: Session,
    user_id: int,
    chat_id: int,
    contents: Sequence[str],
) -> list[MemoryCandidate]:
    existing = {
        _normalize_candidate_content(candidate.content): candidate
        for candidate in list_memory_candidates(db, user_id, chat_id)
    }

    changed = False
    for content in contents:
        normalized = _normalize_candidate_content(content)
        if not normalized or normalized in existing:
            continue

        candidate = MemoryCandidate(
            user_id=user_id,
            chat_id=chat_id,
            content=normalized,
            status="pending",
        )
        db.add(candidate)
        changed = True

    if changed:
        db.commit()

    return list_memory_candidates(db, user_id, chat_id)


async def analyze_memory_candidates(
    db: Session,
    client: OllamaClient,
    model: str,
    chat: Chat,
) -> list[MemoryCandidate]:
    memories = list_memories(db, chat.user_id)
    messages = db.exec(
        select(Message)
        .where(Message.chat_id == chat.id)
        .where(Message.is_complete.is_(True))
        .where(Message.role.in_(["user", "assistant"]))
        .order_by(Message.created_at, Message.id)
    ).all()
    existing_candidates = list_memory_candidates(db, chat.user_id, chat.id)
    contents = await generate_memory_candidate_contents(
        client,
        model,
        chat,
        messages,
        memories,
        existing_candidates,
    )
    return upsert_memory_candidates(db, chat.user_id, chat.id, contents)
