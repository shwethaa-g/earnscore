"""Application settings, read from environment variables (see .env.example)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"), extra="ignore")

    env: str = "development"  # development | production
    secret_key: str = "change-me-in-env"
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'data' / 'earnscore.db').as_posix()}"
    data_dir: Path = BACKEND_DIR / "data"
    upload_dir: Path = BACKEND_DIR / "data" / "uploads"
    frontend_dist: Path = BACKEND_DIR.parent / "frontend" / "dist"
    allowed_origin: str = "http://localhost:5173"
    session_hours: int = 12
    max_upload_mb: int = 10
    consent_default_days: int = 90
    consent_purge_days: int = 7

    llm_provider: str = "gemini"  # gemini | none
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    seed_admin_email: str = ""
    seed_admin_password: str = ""
    seed_officer_email: str = ""
    seed_officer_password: str = ""
    seed_worker_email: str = ""
    seed_worker_password: str = ""

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    return s
