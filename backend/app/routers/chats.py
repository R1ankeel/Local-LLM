from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlmodel import Session, select, delete

from app.core.time import utc_now
from app.db import get_db
from app.dependencies import get_current_user
from app.models.auth import User
from app.models.behavior_profile import BehaviorProfile, BehaviorProfileSummary
from app.models.chat import (
    Chat,
    ChatCreateRequest,
    ChatDetailRead,
    ChatRead,
    ChatUpdateRequest,
    Message,
    MessageRead,
)
from app.services.behavior_profiles import ensure_default_profile


router = APIRouter(prefix="/chats")


def _normalize_title(title: str | None) -> str:
    cleaned = " ".join((title or "").split()).strip()
    return cleaned[:120] if cleaned else "Новый чат"


def _get_owned_chat(db: Session, chat_id: int, user_id: int) -> Chat:
    chat = db.get(Chat, chat_id)
    if not chat or chat.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Чат не найден.")
    return chat


def _get_owned_profile(db: Session, profile_id: int, user_id: int) -> BehaviorProfile:
    profile = db.get(BehaviorProfile, profile_id)
    if not profile or profile.owner_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Профиль не найден.")
    return profile


def _chat_profile(db: Session, chat: Chat) -> BehaviorProfile:
    if chat.profile_id is not None:
        profile = db.get(BehaviorProfile, chat.profile_id)
        if profile and profile.owner_id == chat.user_id:
            return profile
    return ensure_default_profile(db, chat.user_id)


def _chat_to_read(db: Session, chat: Chat) -> ChatRead:
    profile = _chat_profile(db, chat)
    return ChatRead(
        id=chat.id,
        title=chat.title,
        profile_id=chat.profile_id if chat.profile_id is not None else profile.id,
        context_message_limit=chat.context_message_limit,
        profile=BehaviorProfileSummary.model_validate(profile),
        has_context_summary=bool(chat.context_summary and chat.context_summary.strip()),
        summary_updated_at=chat.summary_updated_at,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
    )


def _messages_for_chat(db: Session, chat_id: int) -> list[MessageRead]:
    messages = db.exec(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at, Message.id)
    ).all()
    return [
        MessageRead.model_validate(message)
        for message in messages
        if message.role in {"user", "assistant"}
    ]


@router.get("", response_model=list[ChatRead])
def list_chats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chats = db.exec(
        select(Chat)
        .where(Chat.user_id == current_user.id)
        .order_by(Chat.updated_at.desc(), Chat.created_at.desc(), Chat.id.desc())
    ).all()
    return [_chat_to_read(db, chat) for chat in chats]


@router.post("", response_model=ChatRead, status_code=status.HTTP_201_CREATED)
def create_chat(
    payload: ChatCreateRequest | None = Body(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = None
    if payload and payload.profile_id is not None:
        profile = _get_owned_profile(db, payload.profile_id, current_user.id)
    else:
        profile = ensure_default_profile(db, current_user.id)

    chat = Chat(
        user_id=current_user.id,
        profile_id=profile.id,
        context_message_limit=payload.context_message_limit if payload else 40,
        title=_normalize_title(payload.title if payload else None),
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return _chat_to_read(db, chat)


@router.get("/{chat_id}", response_model=ChatDetailRead)
def get_chat(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat = _get_owned_chat(db, chat_id, current_user.id)
    chat_read = _chat_to_read(db, chat)
    return ChatDetailRead(**chat_read.model_dump(), messages=_messages_for_chat(db, chat.id))


@router.patch("/{chat_id}", response_model=ChatRead)
def update_chat(
    chat_id: int,
    payload: ChatUpdateRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat = _get_owned_chat(db, chat_id, current_user.id)

    changed = False

    if "profile_id" in payload.model_fields_set:
        if payload.profile_id is None:
            profile = ensure_default_profile(db, current_user.id)
        else:
            profile = _get_owned_profile(db, payload.profile_id, current_user.id)

        if chat.profile_id != profile.id:
            chat.profile_id = profile.id
            changed = True

    if "context_message_limit" in payload.model_fields_set and payload.context_message_limit is not None:
        if chat.context_message_limit != payload.context_message_limit:
            chat.context_message_limit = payload.context_message_limit
            changed = True

    if changed:
        chat.updated_at = utc_now()
        db.add(chat)
        db.commit()
        db.refresh(chat)
    return _chat_to_read(db, chat)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat = _get_owned_chat(db, chat_id, current_user.id)
    db.exec(delete(Message).where(Message.chat_id == chat.id))
    db.delete(chat)
    db.commit()
    return None


def touch_chat_title(chat: Chat, content: str) -> None:
    if chat.title != "Новый чат":
        return

    snippet = " ".join(content.split()).strip()
    if not snippet:
        return

    chat.title = snippet[:80]
    chat.updated_at = utc_now()
