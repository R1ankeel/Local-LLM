from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.clients.ollama import OllamaResponseError, OllamaTimeoutError, OllamaUnavailableError
from app.dependencies import get_current_user
from app.models.auth import User
from app.models.ollama import OllamaModelRead, OllamaModelsRead


router = APIRouter(prefix="/models")


@router.get("", response_model=OllamaModelsRead)
async def list_models(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    client = request.app.state.ollama_client
    manager = request.app.state.model_manager

    try:
        models = await client.list_models()
    except (OllamaUnavailableError, OllamaTimeoutError):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Ollama is unavailable")
    except OllamaResponseError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Ollama returned an error response")

    return OllamaModelsRead(
        models=[OllamaModelRead.model_validate(model) for model in models],
        active_model=manager.active_model,
    )
