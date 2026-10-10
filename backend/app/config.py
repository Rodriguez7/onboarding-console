from functools import cached_property

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./onboarding.db"
    cors_origins: str = "http://localhost:3000"
    webhook_timeout_seconds: float = 5.0
    max_upload_bytes: int = 5 * 1024 * 1024
    max_import_rows: int = 50_000

    @cached_property
    def sqlalchemy_url(self) -> str:
        """Railway/Heroku style URLs use postgres:// — point SQLAlchemy at psycopg 3."""
        url = self.database_url
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
