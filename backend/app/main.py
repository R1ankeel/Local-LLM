from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.clients.ollama import OllamaClient
from app.core.config import (
    FRONTEND_DIST_PATH,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    SERVE_FRONTEND,
)
from app.routers.chat import router as chat_router
from app.routers.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ollama_client = OllamaClient(OLLAMA_BASE_URL, OLLAMA_MODEL)
    try:
        yield
    finally:
        await app.state.ollama_client.aclose()


app = FastAPI(title="Local AI Chat", version="0.2.0", lifespan=lifespan)
app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(chat_router, prefix="/api", tags=["chat"])


if SERVE_FRONTEND and FRONTEND_DIST_PATH.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_PATH, html=True), name="frontend")
