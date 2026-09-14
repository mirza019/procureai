from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application configuration sourced from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "ProcureAI"
    app_env: Literal["development", "test", "production"] = "development"
    demo_mode: bool = True
    database_url: str = "sqlite:///./procureai.db"
    secret_key: str = "development-only-secret-change-before-production"
    access_token_expire_minutes: int = Field(60, ge=5, le=1440)
    cors_origins: str = "http://localhost:8080"
    llm_provider: Literal["gemini", "ollama"] = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    storage_provider: Literal["local", "azure"] = "local"
    local_storage_path: Path = Path("reports")
    azure_storage_connection_string: str = ""
    azure_storage_container: str = "procureai"
    applicationinsights_connection_string: str = ""

    @field_validator("secret_key")
    @classmethod
    def secure_production_key(cls, value: str, info):
        if info.data.get("app_env") == "production" and len(value) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 characters in production")
        return value

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
