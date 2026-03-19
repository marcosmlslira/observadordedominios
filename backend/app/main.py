from fastapi import FastAPI
from contextlib import asynccontextmanager
import logging

from app.api import health
from app.api.v1.routers import czds_ingestion

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

app.include_router(health.router)
app.include_router(czds_ingestion.router)
