from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel
from starlette.responses import JSONResponse

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["reliability-agent-backend"] = "reliability-agent-backend"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report process liveness; this does not check monitored systems or providers."""
    return HealthResponse()


@router.get("/ready")
async def readiness(request: Request):
    """Release readiness, not monitored-system health. Never exposes configuration."""
    config = request.app.state.settings
    ready = config.operations_access_enabled and await request.app.state.history.readiness()
    return JSONResponse(
        {"status": "ready" if ready else "not_ready"}, status_code=200 if ready else 503
    )
