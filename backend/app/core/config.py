"""Application settings using pydantic-settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration loaded from environment variables."""

    # ── General ──────────────────────────────────────────────
    ENVIRONMENT: str = "development"
    APP_TITLE: str = "Observador de Domínios — Backend API"

    # ── Admin Auth ──────────────────────────────────────────
    ADMIN_EMAIL: str = "admin@observador.com"
    ADMIN_PASSWORD_HASH: str = ""
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # ── CORS ───────────────────────────────────────────────
    CORS_ORIGINS: str = (
        "http://localhost:3005,"
        "http://localhost:3000,"
        "https://observadordedominios.com.br,"
        "https://www.observadordedominios.com.br"
    )

    # ── Database ─────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://obs:obs@postgres:5432/obs"

    # ── S3 / MinIO ───────────────────────────────────────────
    S3_BUCKET: str = "observador-zones"
    S3_REGION: str = "us-east-1"
    S3_ENDPOINT_URL: str = "http://minio:9000"
    S3_ACCESS_KEY_ID: str = "minioadmin"
    S3_SECRET_ACCESS_KEY: str = "minioadmin"
    S3_FORCE_PATH_STYLE: bool = True

    # ── CZDS ─────────────────────────────────────────────────
    CZDS_USERNAME: str = ""
    CZDS_PASSWORD: str = ""
    CZDS_ENABLED_TLDS: str = "net,org,info"
    CZDS_SYNC_CRON: str = "0 7 * * *"
    CZDS_FORCE_COOLDOWN_HOURS: int = 24
    CZDS_RUNNING_STALE_MINUTES: int = 180
    CZDS_BASE_URL: str = "https://czds-api.icann.org"

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
