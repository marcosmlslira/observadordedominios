from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.api import health
from app.api.v1.routers import auth, czds_ingestion, ingestion, ingestion_config, monitored_brands, similarity, tools
from app.core.config import settings
from app.infra.database import SessionLocal
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.services.use_cases.tools.registry import register_all_tools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

_STALE_THRESHOLDS = {
    "czds": settings.CZDS_RUNNING_STALE_MINUTES,
    "openintel": settings.OPENINTEL_RUNNING_STALE_MINUTES,
    "certstream": 30,
    "crtsh": 120,
}


def _recover_all_stale_on_startup() -> None:
    """Mark orphaned running runs as failed at API startup.

    Workers recover stale runs when their own cycle starts, but if only the API
    restarts (not the worker containers), those runs stay stuck forever.
    This ensures cleanup happens on every API restart too.
    """
    db = SessionLocal()
    try:
        run_repo = IngestionRunRepository(db)
        total = 0
        for source, threshold in _STALE_THRESHOLDS.items():
            recovered = run_repo.recover_all_stale_for_source(source, stale_after_minutes=threshold)
            if recovered:
                logger.info(
                    "Startup stale recovery: marked %d %s run(s) as failed: %s",
                    len(recovered),
                    source,
                    [r.tld for r in recovered],
                )
                total += len(recovered)
        if total:
            db.commit()
    except Exception:
        logger.warning("Startup stale recovery failed", exc_info=True)
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Backend API starting up…")
    _recover_all_stale_on_startup()
    yield
    logger.info("Backend API shutting down…")


app = FastAPI(
    title="Observador de Domínios — Backend API",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(czds_ingestion.router)
app.include_router(ingestion.router)
app.include_router(ingestion_config.router)
app.include_router(monitored_brands.router)
app.include_router(similarity.router)
app.include_router(tools.router)
app.include_router(tools.public_router)

# Register free tool services
register_all_tools()
