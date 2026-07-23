from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator
import asyncio
import json
import logging
import time

import httpx


logger = logging.getLogger(__name__)


class OllamaUnavailableError(Exception):
    pass


class OllamaTimeoutError(Exception):
    pass


class OllamaResponseError(Exception):
    pass


class OllamaModelNotFoundError(Exception):
    pass


class OllamaStreamEndedWithoutDoneError(Exception):
    pass


class OllamaClient:
    def __init__(self, base_url: str, default_model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(60.0, connect=5.0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get_json(self, path: str) -> dict:
        try:
            response = await self._client.get(path)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError("Истекло время ожидания запроса к Ollama.") from exc
        except httpx.RequestError as exc:
            raise OllamaUnavailableError("Ollama недоступна.") from exc
        except httpx.HTTPStatusError as exc:
            raise OllamaResponseError("Ollama вернула ошибочный ответ.") from exc

    async def _post_json(self, path: str, payload: dict) -> dict:
        try:
            response = await self._client.post(path, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError("Истекло время ожидания запроса к Ollama.") from exc
        except httpx.RequestError as exc:
            raise OllamaUnavailableError("Ollama недоступна.") from exc
        except httpx.HTTPStatusError as exc:
            raise OllamaResponseError("Ollama вернула ошибочный ответ.") from exc

    async def list_models(self) -> list[dict]:
        payload = await self._get_json("/api/tags")
        models = []
        for item in payload.get("models", []):
            if not isinstance(item, dict):
                continue

            name = item.get("name") or item.get("model")
            if not name:
                continue

            models.append(
                {
                    "name": name,
                    "size": item.get("size"),
                    "modified_at": item.get("modified_at"),
                }
            )
        return models

    async def list_running_models(self) -> list[dict]:
        payload = await self._get_json("/api/ps")
        models = payload.get("models", [])
        return [item for item in models if isinstance(item, dict)]

    async def ensure_model_available(self, model: str) -> None:
        models = await self.list_models()
        if any(item.get("name") == model for item in models):
            return

        raise OllamaModelNotFoundError(f"Модель '{model}' недоступна в Ollama.")

    async def get_health(self, active_model: str) -> dict:
        models = await self.list_models()
        model_available = any(item.get("name") == active_model for item in models)
        return {
            "ollama": "ok",
            "model": active_model,
            "model_available": model_available,
        }

    async def preload_model(self, model: str) -> dict:
        return await self._post_json(
            "/api/generate",
            {
                "model": model,
                "prompt": "",
                "stream": False,
                "keep_alive": -1,
            },
        )

    async def unload_model(self, model: str) -> dict:
        return await self._post_json(
            "/api/generate",
            {
                "model": model,
                "prompt": "",
                "stream": False,
                "keep_alive": 0,
            },
        )

    async def wait_until_unloaded(self, model: str, timeout_seconds: float = 30.0) -> None:
        started_at = time.monotonic()
        while True:
            running = await self.list_running_models()
            if not any(item.get("name") == model or item.get("model") == model for item in running):
                return

            if time.monotonic() - started_at >= timeout_seconds:
                raise OllamaTimeoutError(f"Истекло время ожидания выгрузки модели '{model}'.")

            await asyncio.sleep(0.5)

    async def switch_active_model(self, current_model: str, next_model: str) -> str:
        if current_model == next_model:
            return current_model

        await self.ensure_model_available(next_model)
        await self.unload_model(current_model)
        await self.wait_until_unloaded(current_model)

        try:
            await self.preload_model(next_model)
        except Exception:
            try:
                await self.preload_model(current_model)
            except Exception:
                logger.exception("Failed to restore previous model after preload error")
            raise

        return next_model

    @asynccontextmanager
    async def stream_chat(
        self,
        model: str,
        messages: list[dict],
        think: bool,
    ) -> AsyncIterator[httpx.Response]:
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "think": think,
        }

        try:
            async with self._client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                yield response
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError("Истекло время ожидания ответа Ollama.") from exc
        except httpx.RequestError as exc:
            raise OllamaUnavailableError("Ollama недоступна.") from exc
        except httpx.HTTPStatusError as exc:
            raise OllamaResponseError("Ollama вернула ошибочный ответ.") from exc

    async def iter_content(self, response: httpx.Response) -> AsyncIterator[str]:
        seen_done = False
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
                seen_done = True
                break

        if not seen_done:
            raise OllamaStreamEndedWithoutDoneError("Ollama stream ended before done=true.")
