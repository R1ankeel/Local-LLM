from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlmodel import Session, delete, select

from app.db import get_db
from app.dependencies import get_current_user, utc_now
from app.models.auth import User
from app.models.chat import Chat, ChatCreateRequest, ChatDetailRead, ChatRead, Message, MessageRead


router = APIRouter(prefix="/chats")


def _normalize_title(title: str | None) -> str:
    cleaned = " ".join((title or "").split()).strip()
    return cleaned[:120] if cleaned else "New chat"


def _get_owned_chat(db: Session, chat_id: int, user_id: int) -> Chat:
    chat = db.get(Chat, chat_id)
    if not chat or chat.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


def _chat_to_read(chat: Chat) -> ChatRead:
    return ChatRead.model_validate(chat)


def _messages_for_chat(db: Session, chat_id: int) -> list[MessageRead]:
    messages = db.exec(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at, Message.id)
    ).all()
    return [MessageRead.model_validate(message) for message in messages]


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
    return [_chat_to_read(chat) for chat in chats]


@router.post("", response_model=ChatRead, status_code=status.HTTP_201_CREATED)
def create_chat(
    payload: ChatCreateRequest | None = Body(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat = Chat(
        user_id=current_user.id,
        title=_normalize_title(payload.title if payload else None),
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return _chat_to_read(chat)


@router.get("/{chat_id}", response_model=ChatDetailRead)
def get_chat(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat = _get_owned_chat(db, chat_id, current_user.id)
    return ChatDetailRead(**_chat_to_read(chat).model_dump(), messages=_messages_for_chat(db, chat.id))


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
    if chat.title != "New chat":
        return

    snippet = " ".join(content.split()).strip()
    if not snippet:
        return

    chat.title = snippet[:80]
    chat.updated_at = utc_now()
