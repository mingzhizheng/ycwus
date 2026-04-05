from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://dyms:dyms_dev_2026@db:5432/dyms"
    DATABASE_URL_SYNC: str = "postgresql://dyms:dyms_dev_2026@db:5432/dyms"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # JWT
    JWT_SECRET: str = "your-256-bit-secret-change-in-production"
    JWT_ACCESS_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # File Storage
    UPLOAD_DIR: str = "/uploads"
    UPLOAD_MAX_SIZE_MB: int = 20
    CLOUD_BACKUP_ENABLED: bool = False
    AWS_BUCKET: Optional[str] = None
    AWS_REGION: Optional[str] = None

    # Email
    SMTP_HOST: str = "mailhog"
    SMTP_PORT: int = 1025
    SMTP_FROM: str = "noreply@dyms.local"
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_USE_TLS: bool = False

    # Application
    DEFAULT_FACILITY_ID: int = 1
    APP_ENV: str = "development"
    LOG_LEVEL: str = "DEBUG"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
