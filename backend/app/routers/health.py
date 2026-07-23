from fastapi import APIRouter, Request

from app.clients.ollama import (
    OllamaResponseError,
    OllamaTimeoutError,
    OllamaUnavailableError,
)


router = APIRouter()


@router.get("/health")
async def health(request: Request):
    client = request.app.state.ollama_client
    payload = {
        "app": "ok",
        "ollama": "unavailable",
        "model": client.model,
        "model_available": False,
    }

    try:
        ollama_health = await client.get_health()
    except (OllamaUnavailableError, OllamaTimeoutError, OllamaResponseError):
        return payload

    payload.update(ollama_health)
    return payload
