from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OllamaModelRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    size: int | None = None
    modified_at: datetime | None = None


class OllamaModelsRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: list[OllamaModelRead]
    active_model: str
