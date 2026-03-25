from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.api import health
from app.api.v1.routers import auth, czds_ingestion, ingestion, monitored_brands, similarity, tools
from app.core.config import settings
from app.services.use_cases.tools.registry import register_all_tools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logging.getLogger(__name__).info("Backend API starting up…")
    yield
    logging.getLogger(__name__).info("Backend API shutting down…")


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
app.include_router(monitored_brands.router)
app.include_router(similarity.router)
app.include_router(tools.router)
app.include_router(tools.public_router)

# Register free tool services
register_all_tools()
