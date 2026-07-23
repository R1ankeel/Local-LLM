from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Column, DateTime, Index, String, text
from sqlmodel import Field as SQLField, SQLModel

from app.core.time import utc_now


class BehaviorProfile(SQLModel, table=True):
    __tablename__ = "behavior_profiles"
    __table_args__ = (
        Index(
            "ux_behavior_profiles_owner_default",
            "owner_id",
            unique=True,
            sqlite_where=text("is_default = 1"),
        ),
    )

    id: int | None = SQLField(default=None, primary_key=True)
    owner_id: int = SQLField(foreign_key="users.id", index=True, nullable=False)
    name: str = SQLField(sa_column=Column(String(120), nullable=False))
    description: str = SQLField(sa_column=Column(String(240), nullable=False, default=""))
    instructions: str = SQLField(sa_column=Column(String(8000), nullable=False))
    is_default: bool = SQLField(default=False, nullable=False, index=True)
    created_at: datetime = SQLField(
        sa_column=Column(DateTime(timezone=False), nullable=False),
        default_factory=utc_now,
    )
    updated_at: datetime = SQLField(
        sa_column=Column(DateTime(timezone=False), nullable=False, index=True),
        default_factory=utc_now,
    )


class BehaviorProfileBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=240)
    instructions: str | None = Field(default=None, max_length=8000)
    is_default: bool | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("Название профиля не должно быть пустым.")
        return cleaned

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str:
        if value is None:
            return ""
        return value.strip()

    @field_validator("instructions")
    @classmethod
    def normalize_instructions(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Инструкции профиля не должны быть пустыми.")
        return cleaned


class BehaviorProfileCreateRequest(BehaviorProfileBase):
    name: str = Field(max_length=120)
    instructions: str = Field(max_length=8000)
    description: str = Field(default="", max_length=240)
    is_default: bool = False


class BehaviorProfileUpdateRequest(BehaviorProfileBase):
    pass


class BehaviorProfileSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    is_default: bool


class BehaviorProfileRead(BehaviorProfileSummary):
    instructions: str
    created_at: datetime
    updated_at: datetime
