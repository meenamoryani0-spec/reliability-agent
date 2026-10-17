from fastapi import APIRouter, HTTPException, Request

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
async def check_infrastructure(request: Request, check_id: str) -> InfrastructureResult:
    adapter = service(request)
    if check_id not in CHECK_IDS:
        raise HTTPException(status_code=404, detail="Infrastructure check is not registered")
    return await adapter.check(check_id)
