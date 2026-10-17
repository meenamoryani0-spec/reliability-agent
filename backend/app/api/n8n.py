from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.api.history import capture_history
from app.tools.n8n_models import Cursor, ExecutionId, N8nReadResult, ResourceId

router = APIRouter(tags=["read-only n8n inspection"])


def service(request: Request):
    if request.app.state.settings.environment == "production":
        raise HTTPException(
            status_code=404, detail="n8n inspection requires deployment access controls"
        )
    return request.app.state.n8n_service


@router.get("/services/n8n")
async def describe_n8n(request: Request) -> dict:
    return service(request).describe()


@router.get("/n8n/workflows", response_model=N8nReadResult)
async def workflows(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
    cursor: Cursor | None = None,
) -> N8nReadResult:
    return await service(request).read("workflows", limit=limit, cursor=cursor)


@router.get("/n8n/executions/failed", response_model=N8nReadResult)
async def failed_executions(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
    cursor: Cursor | None = None,
    workflow_id: ResourceId | None = None,
) -> N8nReadResult:
    return await service(request).read(
        "failed_executions", limit=limit, cursor=cursor, workflow_id=workflow_id
    )


@router.get("/n8n/executions/{execution_id}", response_model=N8nReadResult)
async def execution(
    execution_id: ExecutionId, request: Request, response: Response
) -> N8nReadResult:
    result = await service(request).read("execution", execution_id=execution_id)
    source = (
        "n8n-fixture-v1"
        if result.synthetic
        else (request.app.state.settings.n8n_base_url or "unconfigured")
    )
    return await capture_history(request, response, result, source)
