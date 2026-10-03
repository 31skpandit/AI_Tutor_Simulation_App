"""Application settings (non-secret). Values come from environment variables or `.env`, prefixed ATS_."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="ATS_",
        extra="ignore",
    )

    data_dir: Path = PROJECT_ROOT / "data"
    models_config: Path = PROJECT_ROOT / "config" / "models.yaml"
    # Overrides budget.monthly_usd_cap in models.yaml when set.
    monthly_budget_usd: float | None = None
    log_level: str = "INFO"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
