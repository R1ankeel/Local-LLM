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
OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "VladimirGav/gemma4-26b-16GB-VRAM:latest",
)
SERVE_FRONTEND = os.getenv("SERVE_FRONTEND", "true").lower() == "true"
FRONTEND_DIST_PATH = _resolve_path(
    os.getenv("FRONTEND_DIST_PATH", "frontend/dist"),
    ROOT_DIR / "frontend" / "dist",
)
