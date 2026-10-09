import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.config import Settings
from app.logging import configure_logging

logger = logging.getLogger("reliability_agent")


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging(config.log_level)
        logger.info("Backend started (environment=%s)", config.environment)
        yield
        logger.info("Backend stopped")

    application = FastAPI(
        title="AI Reliability Agent",
        description="Phase 1 foundation. Health reports backend liveness only.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if config.environment == "production" else "/docs",
        redoc_url=None,
        openapi_url=None if config.environment == "production" else "/openapi.json",
    )
    application.state.settings = config
    application.include_router(health_router)
    return application


app = create_app()
