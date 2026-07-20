from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import candidates, discovery
from app.core.config import settings
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(candidates.router, prefix="/api/v1")
app.include_router(discovery.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "env": settings.deployment_env,
        "llm_provider": settings.resolved_llm_provider,
        "amazon_provider": settings.amazon_provider,
    }
