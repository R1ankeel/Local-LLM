from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlmodel import Field as SQLField, SQLModel

from app.core.time import utc_now
from app.models.behavior_profile import BehaviorProfileSummary
from app.models.web_search import MessageSourceRead


ChatMode = Literal["instant", "thinking"]
MessageRole = Literal["user", "assistant"]
WebSearchMode = Literal["off", "auto", "always"]


class Chat(SQLModel, table=True):
    __tablename__ = "chats"

    id: int | None = SQLField(default=None, primary_key=True)
    user_id: int = SQLField(foreign_key="users.id", index=True, nullable=False)
    profile_id: int | None = SQLField(
        default=None,
        foreign_key="behavior_profiles.id",
        index=True,
        nullable=True,
    )
    context_summary: str | None = SQLField(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    summary_through_message_id: int | None = SQLField(default=None, index=True, nullable=True)
    summary_updated_at: datetime | None = SQLField(
        default=None,
        sa_column=Column(DateTime(timezone=False), nullable=True, index=True),
    )
    context_message_limit: int = SQLField(default=40, nullable=False)
    title: str = SQLField(sa_column=Column(String(120), nullable=False))
    created_at: datetime = SQLField(
        sa_column=Column(DateTime(timezone=False), nullable=False),
        default_factory=utc_now,
    )
    updated_at: datetime = SQLField(
        sa_column=Column(DateTime(timezone=False), nullable=False, index=True),
        default_factory=utc_now,
    )


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: int | None = SQLField(default=None, primary_key=True)
    chat_id: int = SQLField(foreign_key="chats.id", index=True)
    role: MessageRole = SQLField(sa_column=Column(String(16), nullable=False))
    content: str = SQLField(sa_column=Column(String(8000), nullable=False))
    is_complete: bool = SQLField(default=True, sa_column=Column(Boolean, nullable=False))
    created_at: datetime = SQLField(
        sa_column=Column(DateTime(timezone=False), nullable=False),
        default_factory=utc_now,
    )


class ChatCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=120)
    profile_id: int | None = Field(default=None, gt=0)
    context_message_limit: int = Field(default=40, ge=10, le=100)

    @field_validator("profile_id")
    @classmethod
    def profile_id_must_be_positive(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("Идентификатор профиля должен быть больше 0.")
        return value


class ChatUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: int | None = Field(default=None)
    context_message_limit: int | None = Field(default=None, ge=10, le=100)

    @field_validator("profile_id")
    @classmethod
    def profile_id_must_be_positive(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("Идентификатор профиля должен быть больше 0.")
        return value


class ChatTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat_id: int = Field(gt=0)
    content: str = Field(min_length=1, max_length=8000)
    mode: ChatMode = "instant"
    web_search_mode: WebSearchMode = "off"
    use_web_search: bool | None = None

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Сообщение не должно быть пустым.")
        return value


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    role: MessageRole
    content: str
    is_complete: bool
    created_at: datetime
    sources: list[MessageSourceRead] = Field(default_factory=list)


class ChatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    profile_id: int | None
    context_message_limit: int
    profile: BehaviorProfileSummary | None = None
    has_context_summary: bool = False
    summary_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ChatDetailRead(ChatRead):
    messages: list[MessageRead]
