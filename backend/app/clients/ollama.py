from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator
import json
import logging

import httpx


logger = logging.getLogger(__name__)


class OllamaUnavailableError(Exception):
    pass


class OllamaTimeoutError(Exception):
    pass


class OllamaResponseError(Exception):
    pass


class OllamaClient:
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(60.0, connect=5.0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_health(self) -> dict:
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError("Ollama health check timed out") from exc
        except httpx.RequestError as exc:
            raise OllamaUnavailableError("Ollama is unavailable") from exc
        except httpx.HTTPStatusError as exc:
            raise OllamaResponseError("Ollama returned an error response") from exc

        models = payload.get("models", [])
        model_available = any(
            item.get("name") == self.model or item.get("model") == self.model
            for item in models
            if isinstance(item, dict)
        )
        return {
            "ollama": "ok",
            "model": self.model,
            "model_available": model_available,
        }

    @asynccontextmanager
    async def stream_chat(
        self,
        messages: list[dict],
        think: bool,
    ) -> AsyncIterator[httpx.Response]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "think": think,
        }

        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                yield response
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError("Ollama chat timed out") from exc
        except httpx.RequestError as exc:
            raise OllamaUnavailableError("Ollama is unavailable") from exc
        except httpx.HTTPStatusError as exc:
            raise OllamaResponseError("Ollama returned an error response") from exc

    async def iter_content(self, response: httpx.Response) -> AsyncIterator[str]:
        async for line in response.aiter_lines():
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping invalid Ollama line: %s", line)
                continue

            content = payload.get("message", {}).get("content")
            if content:
                yield content

            if payload.get("done"):
                break

