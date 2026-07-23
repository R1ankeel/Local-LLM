from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.clients.ollama import (
    OllamaModelNotFoundError,
    OllamaResponseError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)
from app.db import get_db
from app.dependencies import get_current_user, utc_now
from app.models.auth import User
from app.models.chat import Chat, ChatTurnRequest, Message
from app.routers.chats import _get_owned_chat, touch_chat_title
from app.services.behavior_profiles import build_system_prompt, get_profile_for_chat


router = APIRouter()
logger = logging.getLogger(__name__)


def _ndjson_event(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"


def _ordered_messages(db: Session, chat_id: int) -> list[dict]:
    rows = db.exec(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at, Message.id)
    ).all()
    return [{"role": row.role, "content": row.content} for row in rows if row.role in {"user", "assistant"}]


@router.post("/chat")
async def chat(
    request: Request,
    payload: ChatTurnRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat = _get_owned_chat(db, payload.chat_id, current_user.id)
    client = request.app.state.ollama_client
    model_manager = request.app.state.model_manager
    profile = get_profile_for_chat(db, chat)
    system_prompt = build_system_prompt(profile)

    async def stream():
        assistant_message: Message | None = None
        assistant_text = ""

        async with model_manager.generation() as generation_model:
            try:
                await client.ensure_model_available(generation_model)

                user_message = Message(
                    chat_id=chat.id,
                    role="user",
                    content=payload.content,
                )
                db.add(user_message)
                touch_chat_title(chat, payload.content)
                chat.updated_at = utc_now()
                db.commit()
                db.refresh(chat)

                request_messages = [{"role": "system", "content": system_prompt}] + _ordered_messages(db, chat.id)
                think = payload.mode == "thinking"

                async with client.stream_chat(generation_model, request_messages, think) as response:
                    async for chunk in client.iter_content(response):
                        if await request.is_disconnected():
                            break

                        assistant_text += chunk
                        if assistant_message is None:
                            assistant_message = Message(
                                chat_id=chat.id,
                                role="assistant",
                                content=assistant_text,
                            )
                            db.add(assistant_message)
                        else:
                            assistant_message.content = assistant_text

                        chat.updated_at = utc_now()
                        db.commit()

                        yield _ndjson_event({"type": "content", "content": chunk})

                    if not await request.is_disconnected():
                        yield _ndjson_event({"type": "done"})
            except (OllamaUnavailableError, OllamaTimeoutError, OllamaResponseError) as exc:
                logger.warning("Chat stream failed: %s", exc)
                if not await request.is_disconnected():
                    message = "Ollama недоступна."
                    if isinstance(exc, OllamaTimeoutError):
                        message = "Истекло время ожидания ответа Ollama."
                    elif isinstance(exc, OllamaResponseError):
                        message = "Ollama вернула ошибочный ответ."
                    yield _ndjson_event({"type": "error", "message": message})
            except OllamaModelNotFoundError as exc:
                logger.warning("Active model is unavailable: %s", exc)
                if not await request.is_disconnected():
                    yield _ndjson_event({"type": "error", "message": str(exc)})
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected chat error")
                if not await request.is_disconnected():
                    yield _ndjson_event({"type": "error", "message": "Непредвиденная ошибка при отправке сообщения."})

    return StreamingResponse(stream(), media_type="application/x-ndjson")
