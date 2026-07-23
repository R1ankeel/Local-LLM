from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.clients.ollama import (
    OllamaResponseError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)
from app.models.chat import ChatRequest


router = APIRouter()
logger = logging.getLogger(__name__)


def _ndjson_event(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"


@router.post("/chat")
async def chat(request: Request, payload: ChatRequest):
    client = request.app.state.ollama_client
    request_messages = [message.model_dump() for message in payload.messages]
    think = payload.mode == "thinking"

    async def stream():
        try:
            async with client.stream_chat(request_messages, think) as response:
                async for chunk in client.iter_content(response):
                    if await request.is_disconnected():
                        break
                    yield _ndjson_event({"type": "content", "content": chunk})

                if not await request.is_disconnected():
                    yield _ndjson_event({"type": "done"})
        except (OllamaUnavailableError, OllamaTimeoutError, OllamaResponseError) as exc:
            logger.warning("Chat stream failed: %s", exc)
            if not await request.is_disconnected():
                message = "Ollama недоступна"
                if isinstance(exc, OllamaTimeoutError):
                    message = "Превышено время ожидания ответа Ollama"
                elif isinstance(exc, OllamaResponseError):
                    message = "Ollama вернула ошибку"
                yield _ndjson_event({"type": "error", "message": message})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unexpected chat error")
            if not await request.is_disconnected():
                yield _ndjson_event({"type": "error", "message": "Внутренняя ошибка сервера"})

    return StreamingResponse(stream(), media_type="application/x-ndjson")
