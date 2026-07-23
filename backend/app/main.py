from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app.clients.ollama import OllamaClient
from app.core.config import (
    FRONTEND_DIST_PATH,
    OLLAMA_BASE_URL,
    OLLAMA_DEFAULT_MODEL,
    SERVE_FRONTEND,
)
from app.db import init_db
from app.routers.auth import router as auth_router
from app.routers.chat import router as chat_router
from app.routers.chats import router as chats_router
from app.routers.health import router as health_router
from app.routers.models import router as models_router
from app.routers.profiles import router as profiles_router
from app.services.model_manager import ModelManager


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope) -> Response:
        if path.startswith('api'):
            return await super().get_response(path, scope)

        try:
            response = await super().get_response(path, scope)
        except Exception:
            response = None

        if response is not None and getattr(response, 'status_code', None) != 404:
            return response

        if '.' in path:
            return await super().get_response(path, scope)

        return await super().get_response('index.html', scope)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.ollama_client = OllamaClient(OLLAMA_BASE_URL, OLLAMA_DEFAULT_MODEL)
    app.state.model_manager = ModelManager(app.state.ollama_client, OLLAMA_DEFAULT_MODEL)
    try:
        yield
    finally:
        await app.state.ollama_client.aclose()


app = FastAPI(title='Локальный чат с ИИ', version='0.4.1', lifespan=lifespan)
app.include_router(health_router, prefix='/api', tags=['health'])
app.include_router(auth_router, prefix='/api', tags=['auth'])
app.include_router(chats_router, prefix='/api', tags=['chats'])
app.include_router(profiles_router, prefix='/api', tags=['profiles'])
app.include_router(models_router, prefix='/api', tags=['models'])
app.include_router(chat_router, prefix='/api', tags=['chat'])


if SERVE_FRONTEND and FRONTEND_DIST_PATH.exists():
    app.mount('/', SPAStaticFiles(directory=FRONTEND_DIST_PATH, html=True), name='frontend')


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):  # noqa: ARG001
    return JSONResponse(
        status_code=422,
        content={'detail': 'Запрос содержит некорректные данные.'},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):  # noqa: ARG001
    return JSONResponse(
        status_code=500,
        content={'detail': 'Внутренняя ошибка сервера.'},
    )
