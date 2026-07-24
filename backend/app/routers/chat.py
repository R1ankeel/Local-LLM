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
    OllamaStreamEndedWithoutDoneError,
    OllamaStreamTruncatedError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)
from app.db import get_db
from app.dependencies import get_current_user, utc_now
from app.models.auth import User
from app.models.chat import Chat, ChatTurnRequest, Message
from app.routers.chats import _get_owned_chat, touch_chat_title
from app.services.chat_summaries import SUMMARY_BATCH_SIZE, generate_context_summary
from app.services.behavior_profiles import build_system_prompt, get_profile_for_chat
from app.services.memories import list_memories
from app.services.web_search import (
    build_web_search_prompt,
    replace_message_sources,
    run_duckduckgo_search,
    run_xai_search,
    resolve_web_search_provider,
    WebSearchProviderConfigError,
)
from app.services.web_search_policy import decide_web_search
from app.clients.duckduckgo import DuckDuckGoSearchError
from app.clients.xai import (
    XAIWebSearchError,
)


router = APIRouter()
logger = logging.getLogger(__name__)
CHAT_PROMPT_CHAR_BUDGET = 24000


def _ndjson_event(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"


def _ordered_messages(db: Session, chat_id: int) -> list[dict]:
    rows = db.exec(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at, Message.id)
    ).all()
    return [
        {"role": row.role, "content": row.content}
        for row in rows
        if row.role in {"user", "assistant"} and row.is_complete
    ]


def _ordered_message_rows(db: Session, chat_id: int) -> list[Message]:
    rows = db.exec(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.id)
    ).all()
    return [row for row in rows if row.role in {"user", "assistant"} and row.is_complete]


def _complete_messages_after_cutoff(db: Session, chat: Chat) -> list[Message]:
    messages = _ordered_message_rows(db, chat.id)
    cutoff_id = chat.summary_through_message_id or 0
    if cutoff_id > 0:
        messages = [message for message in messages if (message.id or 0) > cutoff_id]
    return messages


def _raw_window_start(messages: list[Message], context_message_limit: int) -> int:
    if context_message_limit <= 0:
        return len(messages)
    return max(0, len(messages) - context_message_limit)


def _limited_messages(db: Session, chat: Chat) -> list[dict]:
    messages = _complete_messages_after_cutoff(db, chat)
    raw_start = _raw_window_start(messages, chat.context_message_limit)
    selected = messages[raw_start:]
    while selected and selected[0].role == "assistant":
        selected = selected[1:]
    return [{"role": row.role, "content": row.content} for row in selected]


def _prompt_char_length(messages: list[dict]) -> int:
    return sum(len(message.get("role", "")) + len(message.get("content", "")) for message in messages)


def _trim_prompt_to_budget(messages: list[dict]) -> list[dict]:
    if _prompt_char_length(messages) <= CHAT_PROMPT_CHAR_BUDGET:
        return messages

    trimmed = list(messages)
    while len(trimmed) > 1 and _prompt_char_length(trimmed) > CHAT_PROMPT_CHAR_BUDGET:
        trimmed.pop(1)

        while len(trimmed) > 1 and trimmed[1].get("role") == "assistant" and _prompt_char_length(trimmed) > CHAT_PROMPT_CHAR_BUDGET:
            trimmed.pop(1)

    return trimmed


async def _maybe_update_chat_summary(
    db: Session,
    chat: Chat,
    client,
    model: str,
) -> bool:
    messages = _complete_messages_after_cutoff(db, chat)
    raw_start = _raw_window_start(messages, chat.context_message_limit)
    messages = messages[:raw_start]

    if len(messages) < SUMMARY_BATCH_SIZE:
        return False

    batch = messages[:SUMMARY_BATCH_SIZE]
    if batch[-1].role != "assistant":
        return False

    try:
        summary_text = await generate_context_summary(client, model, chat.context_summary, batch)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to update chat summary for chat %s: %s", chat.id, exc)
        return False

    chat.context_summary = summary_text
    chat.summary_through_message_id = batch[-1].id
    chat.summary_updated_at = utc_now()
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return True


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
    active_chat_generations = request.app.state.active_chat_generations

    async def stream():
        assistant_message: Message | None = None
        assistant_text = ""
        web_search_results = []
        active_chat_generations.add(chat.id)
        try:
            async with model_manager.generation() as generation_model:
                try:
                    await client.ensure_model_available(generation_model)

                    await _maybe_update_chat_summary(db, chat, client, generation_model)

                    user_message = Message(
                        chat_id=chat.id,
                        role="user",
                        content=payload.content,
                        is_complete=True,
                    )
                    db.add(user_message)
                    touch_chat_title(chat, payload.content)
                    chat.updated_at = utc_now()
                    db.commit()
                    db.refresh(chat)

                    web_search_decision = decide_web_search(payload)
                    web_search_provider = None

                    if web_search_decision.should_search:
                        try:
                            web_search_provider = resolve_web_search_provider(current_user.web_search_provider)
                            yield _ndjson_event(
                                {
                                    "type": "web_search_started",
                                    "provider": web_search_provider,
                                    "mode": web_search_decision.mode,
                                    "reason_code": web_search_decision.reason_code,
                                }
                            )
                            if web_search_provider == "duckduckgo":
                                web_search_results = await run_duckduckgo_search(
                                    request.app.state.web_search_client,
                                    payload.content,
                                )
                            else:
                                web_search_results = await run_xai_search(
                                    request.app.state.xai_web_search_client,
                                    payload.content,
                                )
                        except (DuckDuckGoSearchError, XAIWebSearchError, WebSearchProviderConfigError) as exc:
                            logger.warning("Web search failed: %s", exc)
                            if not await request.is_disconnected():
                                yield _ndjson_event({"type": "error", "message": "Web search failed."})
                            return

                    memories = list_memories(db, current_user.id)
                    web_search_context = (
                        build_web_search_prompt(payload.content, web_search_results)
                        if web_search_decision.should_search
                        else None
                    )
                    system_prompt = build_system_prompt(
                        profile,
                        chat.context_summary,
                        memories,
                        web_search_context or None,
                    )
                    request_messages = _trim_prompt_to_budget(
                        [{"role": "system", "content": system_prompt}] + _limited_messages(db, chat)
                    )
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
                                    is_complete=False,
                                )
                                db.add(assistant_message)
                            else:
                                assistant_message.content = assistant_text

                            chat.updated_at = utc_now()
                            db.commit()

                            yield _ndjson_event({"type": "content", "content": chunk})

                        if not await request.is_disconnected():
                            if assistant_message is not None:
                                assistant_message.is_complete = True
                                db.add(assistant_message)
                                db.commit()
                                if web_search_results:
                                    replace_message_sources(
                                        db,
                                        assistant_message.id,
                                        web_search_results,
                                    )
                            yield _ndjson_event({"type": "done"})
                except (OllamaUnavailableError, OllamaTimeoutError, OllamaResponseError) as exc:
                    logger.warning("Chat stream failed: %s", exc)
                    if not await request.is_disconnected():
                        message = "Ollama ?????????????????."
                        if isinstance(exc, OllamaTimeoutError):
                            message = "??????????? ???????????????????????????????????? Ollama."
                        elif isinstance(exc, OllamaResponseError):
                            message = "Ollama ????????????? ??????????????? ?????????"
                        yield _ndjson_event({"type": "error", "message": message})
                except OllamaStreamEndedWithoutDoneError as exc:
                    logger.warning("Chat stream ended before done=true: %s", exc)
                    if not await request.is_disconnected():
                        yield _ndjson_event({"type": "error", "message": "Ollama ???????????????????????? ????????????????????????????? ????????????????"})
                except OllamaStreamTruncatedError as exc:
                    logger.warning("Chat stream reached generation limit: %s", exc)
                    if not await request.is_disconnected():
                        yield _ndjson_event({"type": "error", "message": "Ответ Ollama достиг лимита генерации."})
                except OllamaModelNotFoundError as exc:
                    logger.warning("Active model is unavailable: %s", exc)
                    if not await request.is_disconnected():
                        yield _ndjson_event({"type": "error", "message": str(exc)})
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Unexpected chat error")
                    if not await request.is_disconnected():
                        yield _ndjson_event({"type": "error", "message": "?????????????????????????????????????? ?????? ??????????????? ????????????????"})
        finally:
            active_chat_generations.discard(chat.id)

    return StreamingResponse(stream(), media_type="application/x-ndjson")
