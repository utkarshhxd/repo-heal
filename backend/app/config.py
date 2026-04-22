from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent

load_dotenv(PROJECT_ROOT / ".env")


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _resolve_path(raw_value: str, base: Path) -> Path:
    path = Path(raw_value)
    if path.is_absolute():
        return path
    return (base / path).resolve()


@dataclass
class Settings:
    backend_url: str
    frontend_url: str
    frontend_origins: list[str]
    github_client_id: str
    github_client_secret: str
    github_callback_url: str
    session_cookie_name: str
    session_cookie_secure: bool
    session_cookie_samesite: str
    session_cookie_domain: str | None
    database_path: Path
    workspace_root: Path
    gemini_api_key: str
    gemini_model: str
    git_author_name: str
    git_author_email: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    database_path = _resolve_path(os.getenv("DATABASE_PATH", "backend/data/app.db"), PROJECT_ROOT)
    workspace_root = _resolve_path(os.getenv("WORKSPACE_ROOT", "backend/data/workspaces"), PROJECT_ROOT)
    frontend_origins_raw = os.getenv("FRONTEND_URL", "http://localhost:3000")
    frontend_origins = [origin.strip().rstrip("/") for origin in frontend_origins_raw.split(",") if origin.strip()]
    session_cookie_domain = (os.getenv("SESSION_COOKIE_DOMAIN") or "").strip() or None

    return Settings(
        backend_url=os.getenv("BACKEND_URL", "http://localhost:8000"),
        frontend_url=frontend_origins[0] if frontend_origins else "http://localhost:3000",
        frontend_origins=frontend_origins or ["http://localhost:3000"],
        github_client_id=os.getenv("GITHUB_CLIENT_ID", ""),
        github_client_secret=os.getenv("GITHUB_CLIENT_SECRET", ""),
        github_callback_url=os.getenv("GITHUB_CALLBACK_URL", "http://localhost:8000/auth/github/callback"),
        session_cookie_name=os.getenv("SESSION_COOKIE_NAME", "repo_agent_session"),
        session_cookie_secure=_to_bool(os.getenv("SESSION_COOKIE_SECURE"), default=False),
        session_cookie_samesite=os.getenv("SESSION_COOKIE_SAMESITE", "lax"),
        session_cookie_domain=session_cookie_domain,
        database_path=database_path,
        workspace_root=workspace_root,
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        git_author_name=os.getenv("GIT_AUTHOR_NAME", "Repo Agent"),
        git_author_email=os.getenv("GIT_AUTHOR_EMAIL", "repo-agent@local.dev"),
    )
