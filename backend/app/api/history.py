from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.db.repository import StorageError
from app.tools.models import CheckStatus

router = APIRouter(tags=["stored reliability history"])
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=10000)]


async def capture_history(request: Request, response: Response, result, source: str):
    capture = await request.app.state.history.capture(result, source)
    response.headers["X-History-Status"] = capture.status
    if capture.check_id:
        response.headers["X-Check-Id"] = capture.check_id
    response.headers["X-Incident-Status"] = capture.incident.status
    if capture.incident.incident_id:
        response.headers["X-Incident-Id"] = capture.incident.incident_id
    return result


def require_local_access(request):
    if request.app.state.settings.environment == "production":
        raise HTTPException(status_code=404, detail="History requires deployment access controls")


async def read(request, operation, **kwargs):
    require_local_access(request)
    try:
        return await request.app.state.history.read(operation, **kwargs)
    except StorageError as error:
        raise HTTPException(status_code=503, detail=error.code) from None


@router.get("/storage")
async def describe_storage(request: Request):
    require_local_access(request)
    import asyncio

    await asyncio.to_thread(request.app.state.history.verify)
    return request.app.state.history.describe()


@router.get("/history/services")
async def services(
    request: Request, limit: Limit = 25, offset: Offset = 0, synthetic: bool | None = None
):
    return await read(request, "services", limit=limit, offset=offset, synthetic=synthetic)


@router.get("/history/checks")
async def checks(
    request: Request,
    limit: Limit = 25,
    offset: Offset = 0,
    service_id: UUID | None = None,
    status: CheckStatus | None = None,
    synthetic: bool | None = None,
):
    return await read(
        request,
        "checks",
        limit=limit,
        offset=offset,
        service_id=service_id,
        status=status,
        synthetic=synthetic,
    )


@router.get("/history/checks/{check_id}")
async def check(request: Request, check_id: UUID):
    result = await read(request, "check", check_id=check_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Stored check not found")
    return result


@router.get("/history/incidents")
async def incidents(
    request: Request,
    limit: Limit = 25,
    offset: Offset = 0,
    service_id: UUID | None = None,
    synthetic: bool | None = None,
):
    return await read(
        request, "incidents", limit=limit, offset=offset, service_id=service_id, synthetic=synthetic
    )


@router.get("/history/incidents/{incident_id}")
async def incident(request: Request, incident_id: UUID):
    result = await read(request, "incident", incident_id=incident_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Stored incident not found")
    return result


@router.get("/history/incidents/{incident_id}/observations")
async def incident_observations(
    request: Request, incident_id: UUID, limit: Limit = 25, offset: Offset = 0
):
    if await read(request, "incident", incident_id=incident_id) is None:
        raise HTTPException(status_code=404, detail="Stored incident not found")
    return await read(
        request, "incident_observations", incident_id=incident_id, limit=limit, offset=offset
    )


@router.get("/history/incidents/{incident_id}/assessments")
async def incident_assessments(
    request: Request, incident_id: UUID, limit: Limit = 25, offset: Offset = 0
):
    if await read(request, "incident", incident_id=incident_id) is None:
        raise HTTPException(status_code=404, detail="Stored incident not found")
    return await read(
        request, "incident_assessments", incident_id=incident_id, limit=limit, offset=offset
    )
