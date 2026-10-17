from fastapi import APIRouter, HTTPException, Request, Response

from app.api.history import capture_history
from app.tools.infrastructure_models import CHECK_IDS, InfrastructureResult

router = APIRouter(tags=["read-only infrastructure checks"])


def service(request: Request):
    if request.app.state.settings.environment == "production":
        raise HTTPException(
            status_code=404, detail="Infrastructure inspection requires deployment access controls"
        )
    return request.app.state.infrastructure_service


@router.get("/services/infrastructure")
async def describe_infrastructure(request: Request) -> dict:
    return service(request).describe()


@router.post("/checks/infrastructure/{check_id}", response_model=InfrastructureResult)
async def check_infrastructure(
    request: Request, check_id: str, response: Response
) -> InfrastructureResult:
    adapter = service(request)
    if check_id not in CHECK_IDS:
        raise HTTPException(status_code=404, detail="Infrastructure check is not registered")
    result = await adapter.check(check_id)
    config = request.app.state.settings
    if result.synthetic:
        source = "infrastructure-fixture-v1"
    elif check_id.startswith("vercel"):
        source = "vercel:" + (config.vercel_deployment_id or "unconfigured")
    elif check_id.startswith("supabase"):
        source = "supabase:" + (config.supabase_project_ref or "unconfigured")
    else:
        source = ":".join(
            (
                config.postgres_host or "unconfigured",
                str(config.postgres_port),
                config.postgres_dbname or "",
                config.postgres_user or "",
            )
        )
    return await capture_history(request, response, result, source)
