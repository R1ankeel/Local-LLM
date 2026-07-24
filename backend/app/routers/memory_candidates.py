from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlmodel import Session

from app.clients.ollama import (
    OllamaModelNotFoundError,
    OllamaResponseError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)
from app.db import get_db
from app.dependencies import get_current_user
from app.models.auth import User
from app.models.memory import MemoryCandidate, MemoryCandidateRead, MemoryCandidateReviewRequest
from app.routers.chats import _get_owned_chat
from app.services.memory_candidates import (
    analyze_memory_candidates,
    delete_memory_candidate,
    get_memory_candidate,
    list_memory_candidates,
    update_memory_candidate,
)


router = APIRouter(prefix="/chats/{chat_id}/memory-candidates")


def _candidate_read(candidate: MemoryCandidate) -> MemoryCandidateRead:
    return MemoryCandidateRead.model_validate(candidate)


def _get_owned_candidate(
    db: Session,
    candidate_id: int,
    user_id: int,
    chat_id: int,
) -> MemoryCandidate:
    candidate = get_memory_candidate(db, candidate_id, user_id, chat_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found.")
    return candidate


@router.get("", response_model=list[MemoryCandidateRead])
def get_memory_candidates(
    chat_id: int,
    status: str = Query(default="pending"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_chat(db, chat_id, current_user.id)
    candidates = list_memory_candidates(db, current_user.id, chat_id, status=status)
    return [_candidate_read(candidate) for candidate in candidates]


@router.post("/analyze", response_model=list[MemoryCandidateRead])
async def analyze_memory_candidates_route(
    chat_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat = _get_owned_chat(db, chat_id, current_user.id)
    client = request.app.state.ollama_client
    model_manager = request.app.state.model_manager
    active_chat_generations = request.app.state.active_chat_generations

    if chat.id in active_chat_generations:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Нельзя анализировать кандидатов, пока в этом чате идёт ответ.",
        )

    try:
        async with model_manager.generation() as generation_model:
            await client.ensure_model_available(generation_model)
            candidates = await analyze_memory_candidates(db, client, generation_model, chat)
    except (OllamaUnavailableError, OllamaTimeoutError):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Ollama недоступна.")
    except (OllamaResponseError, OllamaModelNotFoundError, ValueError):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Не удалось проанализировать чат.")

    return [_candidate_read(candidate) for candidate in candidates]


@router.patch("/{candidate_id}", response_model=MemoryCandidateRead)
def patch_memory_candidate(
    chat_id: int,
    candidate_id: int,
    payload: MemoryCandidateReviewRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_chat(db, chat_id, current_user.id)
    candidate = _get_owned_candidate(db, candidate_id, current_user.id, chat_id)
    updated, _ = update_memory_candidate(db, candidate, status=payload.status)
    return _candidate_read(updated)


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_memory_candidate(
    chat_id: int,
    candidate_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_chat(db, chat_id, current_user.id)
    candidate = _get_owned_candidate(db, candidate_id, current_user.id, chat_id)
    delete_memory_candidate(db, candidate)
    return None
