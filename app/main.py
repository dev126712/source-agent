from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import candidates, discovery
from app.core.config import settings
from app.core.logging import configure_logging

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(candidates.router, prefix="/api/v1")
app.include_router(discovery.router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/app/")


# Served same-origin, so the frontend calls /api/v1 with no CORS setup.
# html=True makes StaticFiles return index.html at the mount root.
if WEB_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "env": settings.deployment_env,
        "llm_provider": settings.resolved_llm_provider,
        "amazon_provider": settings.amazon_provider,
    }
