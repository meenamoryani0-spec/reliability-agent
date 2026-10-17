import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.browser import router as browser_router
from app.api.checks import router as checks_router
from app.api.health import router as health_router
from app.api.infrastructure import router as infrastructure_router
from app.api.n8n import router as n8n_router
from app.config import Settings
from app.logging import configure_logging
from app.tools.browser import BrowserChecker
from app.tools.infrastructure import InfrastructureService
from app.tools.n8n import N8nClient, N8nService
from app.tools.n8n_fixtures import fixture_client
from app.tools.website import WebsiteChecker

logger = logging.getLogger("reliability_agent")


def create_app(
    settings: Settings | None = None,
    *,
    website_checker: WebsiteChecker | None = None,
    browser_checker: BrowserChecker | None = None,
    n8n_service: N8nService | None = None,
    infrastructure_service: InfrastructureService | None = None,
) -> FastAPI:
    config = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging(config.log_level)
        logger.info("Backend started (environment=%s)", config.environment)
        yield
        logger.info("Backend stopped")

    application = FastAPI(
        title="AI Reliability Agent",
        description="Read-only reliability checks. Health is backend process liveness only.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if config.environment == "production" else "/docs",
        redoc_url=None,
        openapi_url=None if config.environment == "production" else "/openapi.json",
    )
    application.state.settings = config
    application.state.website_targets = {target.id: target for target in config.website_targets}
    application.state.website_checker = website_checker or WebsiteChecker(
        nameservers=config.website_dns_nameservers
    )
    application.state.browser_checker = browser_checker or BrowserChecker()
    n8n_client = None
    if config.n8n_mode == "fixture":
        n8n_client = fixture_client()
    elif config.n8n_mode == "live" and config.n8n_base_url and config.n8n_api_key:
        n8n_client = N8nClient(
            config.n8n_base_url,
            config.n8n_api_key,
            timeout=config.n8n_timeout_seconds,
            nameservers=config.n8n_dns_nameservers,
        )
    application.state.n8n_service = n8n_service or N8nService(config.n8n_mode, n8n_client)
    application.state.infrastructure_service = infrastructure_service or InfrastructureService(
        config
    )
    application.include_router(health_router)
    application.include_router(checks_router)
    application.include_router(browser_router)
    application.include_router(n8n_router)
    application.include_router(infrastructure_router)
    return application


app = create_app()
