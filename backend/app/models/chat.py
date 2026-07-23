from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Column, DateTime, String
from sqlmodel import Field as SQLField, SQLModel

from app.core.time import utc_now
from app.models.behavior_profile import BehaviorProfileSummary


ChatMode = Literal["instant", "thinking"]
MessageRole = Literal["user", "assistant"]


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
    created_at: datetime = SQLField(
        sa_column=Column(DateTime(timezone=False), nullable=False),
        default_factory=utc_now,
    )


class ChatCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=120)
    profile_id: int | None = Field(default=None, gt=0)

    @field_validator("profile_id")
    @classmethod
    def profile_id_must_be_positive(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("Идентификатор профиля должен быть больше 0.")
        return value


class ChatUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: int | None = Field(default=None)

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
    created_at: datetime


class ChatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    profile_id: int | None
    profile: BehaviorProfileSummary | None = None
    created_at: datetime
    updated_at: datetime


class ChatDetailRead(ChatRead):
    messages: list[MessageRead]
