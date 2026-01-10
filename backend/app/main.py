from fastapi import FastAPI
from app.api import health

app = FastAPI(title="Backend API")

app.include_router(health.router)
