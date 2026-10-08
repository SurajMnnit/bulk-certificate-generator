from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./test.db"
    APP_ENV: str = "development"

    # Storage Configuration
    # Supported values: "local" | "cloudinary"
    STORAGE_PROVIDER: str = "local"
    STORAGE_PATH: str = "storage"  # Used by local provider only

    # CORS Configuration (comma-separated list of allowed origins)
    CORS_ALLOWED_ORIGINS: str = "*"

    # Cloudinary Configuration (required when STORAGE_PROVIDER=cloudinary)
    CLOUDINARY_CLOUD_NAME: Optional[str] = None
    CLOUDINARY_API_KEY: Optional[str] = None
    CLOUDINARY_API_SECRET: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
