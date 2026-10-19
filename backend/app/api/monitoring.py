"""Authenticated operator setup and fixed read checks; no provider-secret writes."""

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.safety import load_object
from app.db.repository import StorageError
from app.security import require_authenticated
from app.tools.models import WebsiteTarget

router = APIRouter(tags=["operator monitoring setup"])


class Registration(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    url: str = Field(min_length=1, max_length=2048)


def target_service(request):
    require_authenticated(request)
    return request.app.state.operator_targets


@router.get("/monitoring")
async def capabilities(request: Request):
    service = target_service(request)
    try:
        targets = await service.all()
        websites = {
            "targets": [target.model_dump(mode="json") for target in targets.values()],
            "error": None,
        }
    except StorageError as error:
        websites = {"targets": [], "error": error.code}
    return {
        "websites": websites,
        "n8n": request.app.state.n8n_service.describe(),
        "infrastructure": request.app.state.infrastructure_service.describe(),
        "automatic_monitoring": False,
    }


@router.post("/monitoring/websites", response_model=WebsiteTarget)
async def register_website(request: Request):
    service = target_service(request)
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(status_code=415, detail="JSON content required")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 4096:
            raise HTTPException(status_code=413, detail="Registration is too large")
        body.extend(chunk)
    try:
        arguments = Registration.model_validate(load_object(bytes(body), 4096))
        target = WebsiteTarget(id="validation", url=arguments.url.strip())
    except (ValidationError, ValueError, TypeError, RecursionError):
        raise HTTPException(
            status_code=422,
            detail="Use a public website URL without credentials or query parameters",
        ) from None
    try:
        return await service.add(target.url)
    except StorageError as error:
        raise HTTPException(
            status_code=409 if error.code == "target_limit_reached" else 503, detail=error.code
        ) from None


@router.post("/monitoring/websites/{target_id}/checks")
async def check_website(request: Request, target_id: str):
    service = target_service(request)
    if service.check_busy:
        raise HTTPException(status_code=409, detail="website_check_busy")
    try:
        target = await service.get(target_id)
    except StorageError:
        raise HTTPException(status_code=503, detail="storage_unavailable") from None
    if target is None:
        raise HTTPException(status_code=404, detail="Website target is not registered")
    # No await between checking and occupying this per-worker slot.
    if service.check_busy:
        raise HTTPException(status_code=409, detail="website_check_busy")
    service.check_busy = True

    async def run():
        try:
            results = []
            checker = request.app.state.website_checker
            for check in (checker.check_http, checker.check_dns, checker.check_ssl):
                result = await check(target)
                saved = await request.app.state.history.capture(result, target.url)
                results.append(
                    {
                        "check": result.model_dump(mode="json"),
                        "history": saved.model_dump(mode="json"),
                    }
                )
            return {"results": results, "automatic_monitoring": False}
        finally:
            service.check_busy = False

    task = asyncio.create_task(run())
    service.pending.add(task)
    task.add_done_callback(service.pending.discard)
    return await asyncio.shield(task)
