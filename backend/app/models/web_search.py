from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlmodel import Field as SQLField, SQLModel

from app.core.time import utc_now


WebSearchProvider = Literal["duckduckgo", "xai"]


class MessageSource(SQLModel, table=True):
    __tablename__ = "message_sources"
    __table_args__ = (
        Index("ix_message_sources_message_id_position", "message_id", "position"),
    )

    id: int | None = SQLField(default=None, primary_key=True)
    message_id: int = SQLField(
        sa_column=Column(
            Integer,
            ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
            index=False,
        )
    )
    position: int = SQLField(sa_column=Column(Integer, nullable=False))
    title: str = SQLField(sa_column=Column(String(240), nullable=False))
    url: str = SQLField(sa_column=Column(String(2048), nullable=False))
    snippet: str = SQLField(sa_column=Column(Text, nullable=False))
    created_at: datetime = SQLField(
        sa_column=Column(DateTime(timezone=False), nullable=False),
        default_factory=utc_now,
    )


class MessageSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message_id: int
    position: int
    title: str
    url: str
    snippet: str
    created_at: datetime
