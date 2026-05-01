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

    # ── Stale-run recovery thresholds (used by main.py startup hook) ─────
    CZDS_RUNNING_STALE_MINUTES: int = 60
    OPENINTEL_RUNNING_STALE_MINUTES: int = 60

    # ── Similarity Worker ──────────────────────────────────────
    SIMILARITY_SCAN_CRON: str = "0 9 * * *"
    SIMILARITY_SCAN_ENABLED: bool = True

    # ── Free Tools ─────────────────────────────────────────────
    TOOLS_DEFAULT_TIMEOUT_SECONDS: int = 30
    TOOLS_SCREENSHOT_TIMEOUT_SECONDS: int = 45
    TOOLS_PLACEHOLDER_ORG_ID: str = "00000000-0000-0000-0000-000000000001"
    GOOGLE_SAFE_BROWSING_API_KEY: str = ""
    PHISHTANK_APP_KEY: str = ""
    URLHAUS_AUTH_TOKEN: str = ""

    # Cache TTLs (seconds)
    TOOLS_CACHE_DNS_LOOKUP: int = 300
    TOOLS_CACHE_WHOIS: int = 86400
    TOOLS_CACHE_SSL_CHECK: int = 3600
    TOOLS_CACHE_SCREENSHOT: int = 1800
    TOOLS_CACHE_SUSPICIOUS_PAGE: int = 1800
    TOOLS_CACHE_HTTP_HEADERS: int = 900
    TOOLS_CACHE_BLACKLIST_CHECK: int = 3600
    TOOLS_CACHE_EMAIL_SECURITY: int = 21600
    TOOLS_CACHE_REVERSE_IP: int = 21600
    TOOLS_CACHE_IP_GEOLOCATION: int = 86400
    TOOLS_CACHE_DOMAIN_SIMILARITY: int = 86400
    TOOLS_CACHE_WEBSITE_CLONE: int = 3600
    TOOLS_CACHE_SUBDOMAIN_TAKEOVER: int = 21600  # 6 horas
    TOOLS_CACHE_SAFE_BROWSING_CHECK: int = 3600
    TOOLS_CACHE_URLHAUS_CHECK: int = 3600
    TOOLS_CACHE_PHISHTANK_CHECK: int = 3600

    # Rate limits (per hour per org)
    TOOLS_RATE_PER_TOOL: int = 30
    TOOLS_RATE_QUICK_ANALYSIS: int = 10
    TOOLS_RATE_GLOBAL: int = 200

    # S3 bucket for tool artifacts (screenshots etc.)
    TOOLS_S3_BUCKET: str = "observador-tools"

    # ── Ingestion Worker Manual Trigger ────────────────────
    # Backend POSTs to the new orchestrator (ingestion/ package) to
    # trigger an out-of-schedule cycle from the admin UI.
    INGESTION_TRIGGER_URLS: str = (
        "http://ingestion_worker:8080/run-now,"
        "http://obs_ingestion_worker:8080/run-now"
    )
    INGESTION_TRIGGER_TIMEOUT_SECONDS: float = 5.0
    INGESTION_MANUAL_TRIGGER_TOKEN: str = ""

    # ── LLM / Groq ────────────────────────────────────────
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # ── LLM / OpenRouter (fallback) ───────────────────────
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_TIMEOUT_SECONDS: float = 20.0
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # ── LLM Feature Flags ────────────────────────────────────
    MATCH_LLM_ASSESSMENT_ENABLED: bool = False
    SEED_LLM_GENERATION_ENABLED: bool = False

    # extra="ignore" so the shared .env (which also feeds the ingestion/
    # service with CZDS credentials etc.) does not break backend startup.
    model_config = {"env_file": ".env", "case_sensitive": True, "extra": "ignore"}


settings = Settings()
