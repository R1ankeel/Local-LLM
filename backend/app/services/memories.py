from __future__ import annotations

from collections.abc import Sequence

from sqlmodel import Session, select

from app.core.prompts import MEMORY_PROMPT_CHAR_LIMIT, MEMORY_PROMPT_HEADER
from app.core.time import utc_now
from app.models.memory import MemoryItem


def list_memories(db: Session, user_id: int) -> list[MemoryItem]:
    return db.exec(
        select(MemoryItem)
        .where(MemoryItem.user_id == user_id)
        .order_by(
            MemoryItem.updated_at.desc(),
            MemoryItem.created_at.desc(),
            MemoryItem.id.desc(),
        )
    ).all()


def get_memory(db: Session, memory_id: int, user_id: int) -> MemoryItem | None:
    memory = db.get(MemoryItem, memory_id)
    if memory is None or memory.user_id != user_id:
        return None
    return memory


def create_memory(db: Session, user_id: int, content: str, is_active: bool = True) -> MemoryItem:
    memory = MemoryItem(user_id=user_id, content=content, is_active=is_active)
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return memory


def update_memory(
    db: Session,
    memory: MemoryItem,
    *,
    content: str | None = None,
    is_active: bool | None = None,
) -> MemoryItem:
    changed = False

    if content is not None and memory.content != content:
        memory.content = content
        changed = True

    if is_active is not None and memory.is_active != is_active:
        memory.is_active = is_active
        changed = True

    if changed:
        memory.updated_at = utc_now()
        db.add(memory)
        db.commit()
        db.refresh(memory)

    return memory


def delete_memory(db: Session, memory: MemoryItem) -> None:
    db.delete(memory)
    db.commit()


def _format_memory_line(content: str) -> str:
    return f"- {content.strip()}"


def select_memory_prompt_lines(memories: Sequence[MemoryItem]) -> list[str]:
    active_memories = [memory for memory in memories if memory.is_active and memory.content.strip()]
    selected_lines: list[str] = [MEMORY_PROMPT_HEADER]

    for memory in active_memories:
        candidate_line = _format_memory_line(memory.content)
        candidate_text = "\n".join(selected_lines + [candidate_line])
        if len(candidate_text) <= MEMORY_PROMPT_CHAR_LIMIT:
            selected_lines.append(candidate_line)
            continue

        if len(selected_lines) == 1:
            selected_lines.append(candidate_line)
        break

    return selected_lines if len(selected_lines) > 1 else []


def build_memory_prompt(memories: Sequence[MemoryItem]) -> str:
    lines = select_memory_prompt_lines(memories)
    return "\n".join(lines) if lines else ""
