from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, DateTime, Index, String
from sqlmodel import Field as SQLField, SQLModel

from app.core.time import utc_now
from app.models.chat import WebSearchMode
from app.models.web_search import WebSearchProvider


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_username", "username", unique=True),)

    id: int | None = SQLField(default=None, primary_key=True)
    username: str = SQLField(sa_column=Column(String(64), nullable=False))
    password_hash: str = SQLField(sa_column=Column(String(255), nullable=False))
    web_search_mode: str = SQLField(
        default="off",
        sa_column=Column(String(8), nullable=False),
    )
    web_search_provider: str = SQLField(
        default="duckduckgo",
        sa_column=Column(String(16), nullable=False),
    )
    created_at: datetime = SQLField(
        sa_column=Column(DateTime(timezone=False), nullable=False),
        default_factory=utc_now,
    )


class Session(SQLModel, table=True):
    __tablename__ = "sessions"

    id: str = SQLField(primary_key=True, max_length=128)
    user_id: int = SQLField(foreign_key="users.id", index=True, nullable=False)
    created_at: datetime = SQLField(
        sa_column=Column(DateTime(timezone=False), nullable=False),
        default_factory=utc_now,
    )
    expires_at: datetime = SQLField(
        sa_column=Column(DateTime(timezone=False), nullable=False, index=True)
    )


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    web_search_mode: WebSearchMode
    web_search_provider: WebSearchProvider
    created_at: datetime


class UserSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    web_search_mode: WebSearchMode = Field(default="off")
    web_search_provider: WebSearchProvider = Field(default="duckduckgo")


UserWebSearchModeUpdate = UserSettingsUpdate
