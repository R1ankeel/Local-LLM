from pathlib import Path
import os

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(ROOT_DIR / ".env")


def _resolve_path(value: str, default: Path) -> Path:
    path = Path(value) if value else default
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path.resolve()


APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_DEFAULT_MODEL = os.getenv(
    "OLLAMA_DEFAULT_MODEL",
    os.getenv("OLLAMA_MODEL", "VladimirGav/gemma4-26b-16GB-VRAM:latest"),
)
WEB_SEARCH_PROVIDER = os.getenv("WEB_SEARCH_PROVIDER", "duckduckgo").strip().lower()
XAI_API_KEY = os.getenv("XAI_API_KEY", "").strip()
XAI_MODEL = os.getenv("XAI_MODEL", "grok-4.5").strip()
XAI_TIMEOUT_SECONDS = float(os.getenv("XAI_TIMEOUT_SECONDS", "30"))
SERVE_FRONTEND = os.getenv("SERVE_FRONTEND", "true").lower() == "true"
FRONTEND_DIST_PATH = _resolve_path(
    os.getenv("FRONTEND_DIST_PATH", "frontend/dist"),
    ROOT_DIR / "frontend" / "dist",
)
DATABASE_PATH = _resolve_path(
    os.getenv("DATABASE_PATH", "backend/data/local_llm.sqlite3"),
    ROOT_DIR / "backend" / "data" / "local_llm.sqlite3",
)
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "local_llm_session")
SESSION_TTL_DAYS = int(os.getenv("SESSION_TTL_DAYS", "7"))
