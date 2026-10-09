from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["reliability-agent-backend"] = "reliability-agent-backend"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report process liveness; this does not check monitored systems or providers."""
    return HealthResponse()
