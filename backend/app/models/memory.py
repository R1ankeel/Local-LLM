from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Boolean, Column, DateTime, String
from sqlmodel import Field as SQLField, SQLModel

from app.core.time import utc_now


class MemoryItem(SQLModel, table=True):
    __tablename__ = "memory_items"

    id: int | None = SQLField(default=None, primary_key=True)
    user_id: int = SQLField(foreign_key="users.id", index=True, nullable=False)
    content: str = SQLField(sa_column=Column(String(500), nullable=False))
    is_active: bool = SQLField(default=True, sa_column=Column(Boolean, nullable=False, index=True))
    created_at: datetime = SQLField(
        sa_column=Column(DateTime(timezone=False), nullable=False, index=True),
        default_factory=utc_now,
    )
    updated_at: datetime = SQLField(
        sa_column=Column(DateTime(timezone=False), nullable=False, index=True),
        default_factory=utc_now,
    )


class MemoryBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str | None) -> str | None:
        if value is None:
            return None

        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Текст записи не должен быть пустым.")
        return cleaned


class MemoryCreateRequest(MemoryBase):
    content: str = Field(max_length=500)
    is_active: bool = True


class MemoryUpdateRequest(MemoryBase):
    pass


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    content: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
