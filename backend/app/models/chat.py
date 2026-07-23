from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


MessageRole = Literal["system", "user", "assistant"]
ChatMode = Literal["instant", "thinking"]


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: MessageRole
    content: str = Field(min_length=1, max_length=8000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    mode: ChatMode = "instant"

