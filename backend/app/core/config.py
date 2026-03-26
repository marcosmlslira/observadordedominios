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
    TARGET_TLDS: str = (
        "com,net,org,xyz,online,site,store,top,info,tech,space,website,fun,"
        "club,vip,icu,live,digital,world,today,email,solutions,services,"
        "support,group,company,center,zone,agency,systems,network,works,"
        "tools,io,ai,dev,app,cloud,software,co,biz,shop,sale,deals,market,"
        "finance,financial,money,credit,loan,bank,capital,fund,exchange,"
        "trading,pay,cash,us,uk,ca,au,de,fr,es,it,nl,eu,asia,news,media,"
        "blog,press,link,click,one,pro,name,life,plus,now,global,expert,"
        "academy,education,school,host,hosting,domains,security,safe,"
        "protect,chat,social,community,team,studio,design,marketing,"
        "consulting,partners,ventures,holdings,international,com.br,net.br,org.br,br"
    )
    CZDS_ENABLED_TLDS: str = (
        "com,net,org,xyz,online,site,store,top,info,tech,space,website,fun,"
        "club,vip,icu,live,digital,world,today,email,solutions,services,"
        "support,group,company,center,zone,agency,systems,network,works,"
        "tools,io,ai,dev,app,cloud,software,co,biz,shop,sale,deals,market,"
        "finance,financial,money,credit,loan,bank,capital,fund,exchange,"
        "trading,pay,cash,us,uk,ca,au,de,fr,es,it,nl,eu,asia,news,media,"
        "blog,press,link,click,one,pro,name,life,plus,now,global,expert,"
        "academy,education,school,host,hosting,domains,security,safe,"
        "protect,chat,social,community,team,studio,design,marketing,"
        "consulting,partners,ventures,holdings,international"
    )
    CZDS_SYNC_CRON: str = "0 7 * * *"
    CZDS_FORCE_COOLDOWN_HOURS: int = 24
    CZDS_RUNNING_STALE_MINUTES: int = 60
    CZDS_BASE_URL: str = "https://czds-api.icann.org"
    CZDS_AUTH_RATE_LIMIT_BACKOFF_SECONDS: int = 300
    CZDS_TLD_FORBIDDEN_SUSPEND_HOURS: int = 168
    CZDS_TLD_NOT_FOUND_SUSPEND_HOURS: int = 168

    # ── CT Logs (CertStream + crt.sh) ──────────────────────────
    CT_CERTSTREAM_URL: str = "ws://certstream_server:8080/"
    CT_CERTSTREAM_ENABLED: bool = True
    CT_CERTSTREAM_RECONNECT_MAX_BACKOFF: int = 60
    CT_BUFFER_FLUSH_SIZE: int = 5000
    CT_BUFFER_FLUSH_SECONDS: int = 30
    CT_CRTSH_ENABLED: bool = True
    CT_FALLBACK_INCLUDE_NON_CZDS: bool = True
    CT_FALLBACK_PRIORITY_TLDS: str = "br,com.br,net.br,org.br,uk,de,fr,au,ca,us,io,ai,co,tv,me"
    CT_STREAM_ENABLED_TLDS: str = ""
    CT_CRTSH_SYNC_CRON: str = "0 5 * * *"
    CT_CRTSH_COOLDOWN_HOURS: int = 20
    CT_CRTSH_QUERY_OVERLAP_HOURS: int = 25
    CT_BR_SUBTLDS: str = "br,com.br,net.br,org.br,gov.br,edu.br,mil.br,app.br,dev.br,log.br,ong.br"
    CT_BULK_MAX_PARALLEL_CHUNKS: int = 2
    CT_BULK_SPLIT_MAX_DEPTH: int = 2
    CT_BULK_RESPONSE_SIZE_LIMIT_MB: int = 8

    # ── Free Tools ─────────────────────────────────────────────
    TOOLS_DEFAULT_TIMEOUT_SECONDS: int = 30
    TOOLS_SCREENSHOT_TIMEOUT_SECONDS: int = 45
    TOOLS_PLACEHOLDER_ORG_ID: str = "00000000-0000-0000-0000-000000000001"

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

    # Rate limits (per hour per org)
    TOOLS_RATE_PER_TOOL: int = 30
    TOOLS_RATE_QUICK_ANALYSIS: int = 10
    TOOLS_RATE_GLOBAL: int = 200

    # S3 bucket for tool artifacts (screenshots etc.)
    TOOLS_S3_BUCKET: str = "observador-tools"

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
