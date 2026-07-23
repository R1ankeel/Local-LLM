from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlmodel import Session

from app.db import get_db
from app.dependencies import get_current_user
from app.models.auth import User
from app.models.memory import (
    MemoryCreateRequest,
    MemoryItem,
    MemoryRead,
    MemoryUpdateRequest,
)
from app.services.memories import create_memory, delete_memory, get_memory, list_memories, update_memory


router = APIRouter(prefix="/memories")


def _get_owned_memory(db: Session, memory_id: int, user_id: int) -> MemoryItem:
    memory = get_memory(db, memory_id, user_id)
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена.")
    return memory


def _memory_read(memory: MemoryItem) -> MemoryRead:
    return MemoryRead.model_validate(memory)


@router.get("", response_model=list[MemoryRead])
def get_memories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    memories = list_memories(db, current_user.id)
    return [_memory_read(memory) for memory in memories]


@router.post("", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
def create_memory_item(
    payload: MemoryCreateRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    memory = create_memory(db, current_user.id, payload.content, payload.is_active)
    return _memory_read(memory)


@router.patch("/{memory_id}", response_model=MemoryRead)
def patch_memory_item(
    memory_id: int,
    payload: MemoryUpdateRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    memory = _get_owned_memory(db, memory_id, current_user.id)
    if not payload.model_fields_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нужно передать хотя бы одно поле для обновления.",
        )

    updated = update_memory(
        db,
        memory,
        content=payload.content if "content" in payload.model_fields_set else None,
        is_active=payload.is_active if "is_active" in payload.model_fields_set else None,
    )
    return _memory_read(updated)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_memory_item(
    memory_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    memory = _get_owned_memory(db, memory_id, current_user.id)
    delete_memory(db, memory)
    return None
